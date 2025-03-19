// 最简代码，也就是这些字段必须有
export default {
  path: "/settings",
  meta: {
    icon: "ep:setting",
    title: "设置"
  },
  children: [
    {
      path: "/settings",
      name: "Settings",
      component: () => import("@/views/settings/wx.vue"),
      meta: {
        title: "设置"
      }
    }
  ]
};
