const app = getApp();

const BATCH_SIZE = 4;       // 每批 4 个人格
const BATCH_INTERVAL = 4000; // 4s 切一次

// 4 套分组主题：按依恋型 D1 前缀（S/MS/MA/A）映射，灵感来自视频参考
// primary = 主色（标题/chips/dot），accent = 浅底（卡片背景）
const GROUP_MAP = {
  S:  { name: '安全型',   tagline: '稳如港湾 · 平和清醒',   primary: '#3A8A8A', accent: '#E8F4F2' },
  MS: { name: '中度安全', tagline: '弹性自如 · 节奏从容',   primary: '#5B73C9', accent: '#ECEFFA' },
  MA: { name: '中度焦虑', tagline: '牵挂温柔 · 在意更深',   primary: '#C9743A', accent: '#FBEFE0' },
  A:  { name: '焦虑型',   tagline: '炽热真诚 · 全心投入',   primary: '#C94F4F', accent: '#FBE4E2' },
};
const DEFAULT_GROUP = { name: '16 种人格', tagline: '看看你是哪一种', primary: '#4FAFAF', accent: '#F2EDE6' };

function inferGroup(types) {
  if (!types || !types.length) return DEFAULT_GROUP;
  const prefix = (types[0].type_code || '').split('-')[0];
  const allSame = types.every((t) => (t.type_code || '').split('-')[0] === prefix);
  return (allSame && GROUP_MAP[prefix]) || DEFAULT_GROUP;
}

Page({
  data: {
    loginReady: false,
    portraits: [],      // 当前批次展示的 4 个
    batchIdx: 0,        // 当前批次：0/1/2/3
    totalBatches: 4,
    portraitsReady: false,
    currentGroup: DEFAULT_GROUP, // 分组主题（颜色/名称/tagline）
  },

  _allTypes: [],
  _rotateTimer: null,

  async onLoad() {
    if (app.globalData.token) {
      this.setData({ loginReady: true });
      this._loadPortraits();
      return;
    }
    // 1) 先试 /auth/dev-login (本地 DEV_MODE 后端的快路径，省 code2session 调用)
    try {
      const res = await app.request({ url: '/auth/dev-login' });
      app.setToken(res.token);
      console.log('[login] dev-login OK');
      this.setData({ loginReady: true });
      this._loadPortraits();
      return;
    } catch (e) {
      console.log('[login] dev-login 不可用，走真实 OAuth', e && e.statusCode);
    }
    // 2) Fallback: tt.login 拿 code → POST /auth/login (真机/生产路径)
    try {
      const loginRes = await new Promise((resolve, reject) => {
        tt.login({
          force: true,
          success: resolve,
          fail: reject,
        });
      });
      if (!loginRes || !loginRes.code) {
        throw new Error('tt.login 未返回 code');
      }
      console.log('[login] tt.login 拿到 code，换 token');
      const res = await app.request({
        url: '/auth/login',
        method: 'POST',
        data: { code: loginRes.code },
      });
      app.setToken(res.token);
      console.log('[login] OAuth 登录 OK');
      this.setData({ loginReady: true });
      this._loadPortraits();
    } catch (e) {
      console.error('[login] 真实登录失败', e);
      tt.showToast({ title: '登录失败，请检查网络后重启', icon: 'none', duration: 3000 });
      this.setData({ loginReady: true });
    }
  },

  onUnload() {
    this._stopRotate();
  },

  onHide() {
    this._stopRotate();
  },

  onShow() {
    if (this._allTypes.length && !this._rotateTimer) {
      this._startRotate();
    }
  },

  async _loadPortraits() {
    try {
      const res = await app.request({ url: '/quiz/types', method: 'GET' });
      const types = (res && res.types) || [];
      if (!types.length) return;
      // 后端已按 id ASC 排序；客户端只负责切批次
      // img_path 与 loading.js 保持同一解析方式："man路径,woman路径" 逗号分隔
      // 首页默认展示 woman（paths[1]），缺失时回落到 paths[0]，再回落到默认路径
      const toUrl = (p) => {
        if (!p) return '';
        return /^https?:\/\//.test(p) ? p : app.baseUrl + p;
      };
      const pickWoman = (imgPath, typeCode) => {
        if (imgPath) {
          const paths = imgPath.split(',').map((s) => s.trim()).filter(Boolean);
          if (paths.length) return paths[1] || paths[0];
        }
        return '/static/personalities/' + typeCode + '_woman.png';
      };
      this._allTypes = types.map((t) => ({
        id: t.id,
        type_code: t.type_code,
        type_name: t.type_name,
        img: toUrl(pickWoman(t.img_path, t.type_code)),
      }));
      const total = Math.ceil(this._allTypes.length / BATCH_SIZE);
      const firstBatch = this._allTypes.slice(0, BATCH_SIZE);
      this.setData({
        portraits: firstBatch,
        batchIdx: 0,
        totalBatches: total,
        portraitsReady: true,
        currentGroup: inferGroup(firstBatch),
      });
      this._startRotate();
    } catch (e) {
      console.warn('[index] 加载人格列表失败', e);
    }
  },

  _startRotate() {
    if (this._rotateTimer || this._allTypes.length <= BATCH_SIZE) return;
    this._rotateTimer = setInterval(() => {
      const total = Math.ceil(this._allTypes.length / BATCH_SIZE);
      const next = (this.data.batchIdx + 1) % total;
      const start = next * BATCH_SIZE;
      const nextBatch = this._allTypes.slice(start, start + BATCH_SIZE);
      this.setData({
        batchIdx: next,
        portraits: nextBatch,
        currentGroup: inferGroup(nextBatch),
      });
    }, BATCH_INTERVAL);
  },

  _stopRotate() {
    if (this._rotateTimer) {
      clearInterval(this._rotateTimer);
      this._rotateTimer = null;
    }
  },

  startQuick() {
    if (!app.globalData.token) {
      tt.showToast({ title: '登录失败，请重启小程序', icon: 'none', duration: 2500 });
      return;
    }
    tt.navigateTo({ url: '/pages/chat/chat' });
  },

  comingSoon() {
    tt.showToast({ title: '敬请期待', icon: 'none', duration: 1500 });
  },

  goHistory() {
    tt.navigateTo({ url: '/pages/history/history' });
  },
});
