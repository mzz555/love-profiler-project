const app = getApp();

Page({
  data: {},

  selectGender(e) {
    const gender = e.currentTarget.dataset.gender;
    tt.navigateTo({ url: '/pages/chat/chat?gender=' + gender });
  },
});
