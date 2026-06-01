import { Navigate } from "react-router-dom";

/** 产物列表已并入聊天页右侧栏；保留路由以便旧链接跳转。 */
export function OutputsPage() {
  return <Navigate to="/" replace />;
}
