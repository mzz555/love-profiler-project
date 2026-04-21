// =====================================================================
// 全局入口 — 存储 token、提供统一 HTTP 请求方法
// 修改 BASE_URL 为生产域名后上线
// =====================================================================

const BASE_URL = 'http://localhost:8000';
const IS_DEV = BASE_URL.includes('localhost');

App({
  isDev: IS_DEV,
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
