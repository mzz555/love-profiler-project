// =====================================================================
// 全局入口 — 存储 token、提供统一 HTTP 请求方法
// 修改 BASE_URL 为生产域名后上线
// =====================================================================

// ── 环境配置 ──────────────────────────────────────────────
// 上线前必须把 PROD_URL 改为真实生产域名（HTTPS）
// 本地开发时改 DEV_URL 为开发机局域网 IP
const DEV_URL  = 'http://192.168.3.179:8000';
const PROD_URL = 'https://your-production-domain.com';

// __wxConfig.envVersion: 'develop' | 'trial' | 'release' (抖音/微信通用)
const ENV_VERSION = (typeof __wxConfig !== 'undefined' && __wxConfig.envVersion) || 'develop';
const BASE_URL = (ENV_VERSION === 'release') ? PROD_URL : DEV_URL;
const IS_DEV = ENV_VERSION !== 'release';

App({
  isDev: IS_DEV,
  baseUrl: BASE_URL,
  globalData: {
    token: null,
    sessionId: null,
    assessmentId: null,
  },

  onLaunch() {
    const token = tt.getStorageSync('token');
    if (token) this.globalData.token = token;

    const sessionId = tt.getStorageSync('sessionId');
    const assessmentId = tt.getStorageSync('assessmentId');
    if (sessionId) {
      this.globalData.sessionId = sessionId;
      this.globalData.assessmentId = assessmentId ? parseInt(assessmentId, 10) : null;
    }
  },

  setToken(token) {
    this.globalData.token = token;
    tt.setStorageSync('token', token);
  },

  clearToken() {
    this.globalData.token = null;
    tt.removeStorageSync('token');
  },

  setSession(sessionId, assessmentId) {
    this.globalData.sessionId = sessionId;
    this.globalData.assessmentId = assessmentId;
    tt.setStorageSync('sessionId', sessionId);
    tt.setStorageSync('assessmentId', String(assessmentId));
  },

  clearSession() {
    this.globalData.sessionId = null;
    this.globalData.assessmentId = null;
    tt.removeStorageSync('sessionId');
    tt.removeStorageSync('assessmentId');
  },

  connectSocket({ path, ticket }) {
    var wsBase = BASE_URL.replace(/^http/, 'ws');
    var url;
    if (ticket) {
      url = wsBase + path + '?ticket=' + encodeURIComponent(ticket);
    } else {
      var token = this.globalData.token;
      url = token
        ? wsBase + path + '?token=' + encodeURIComponent(token)
        : wsBase + path;
    }
    return tt.connectSocket({ url: url });
  },

  /**
   * 统一 HTTP 请求，自动附加 Authorization 头。
   * @returns {Promise<any>} 响应 data
   */
  request({ url, method = 'POST', data = {} }) {
    const token = this.globalData.token;
    return new Promise((resolve, reject) => {
      tt.request({
        url: `${BASE_URL}${url}`,
        method,
        data,
        header: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        success: (res) => {
          if (res.statusCode === 401) {
            this.clearToken();
            tt.redirectTo({ url: '/pages/index/index' });
            reject({ statusCode: 401 });
            return;
          }
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data);
          } else {
            reject({ statusCode: res.statusCode, data: res.data });
          }
        },
        fail: reject,
      });
    });
  },
});
