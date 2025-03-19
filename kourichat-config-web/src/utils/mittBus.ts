import mitt from "mitt";

// 创建事件总线
const emitter = mitt();

// 导出 emitter
export { emitter };
