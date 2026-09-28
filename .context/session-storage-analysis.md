# 登录态存储分析（脱敏）

检查日期：2026-09-27。仅检查用户指定的已登录 Chrome 标签页，未登录、退出、修改存储、重放接口或执行下注。

## 结论

当前会话以页面 origin 下 localStorage 的 `user` JSON 为持久化载体，不是 Cookie 登录。页面和当前 API 域名的 CDP Network.getCookies 均返回空数组（包含 HttpOnly 检查）；sessionStorage 为空。

## 关键字段

| 字段 | 观察与作用 |
|---|---|
| user.token | 长度 2406；已带 `Bearer ` 前缀。JWT 头 typ=JWT、alg=HS256；exp-iat=7200 秒（2 小时）。线上 JS 请求封装将整个字符串写入 authorization 请求头。 |
| user.refreshToken | 长度 2399；无 Bearer 前缀，JWT HS256；exp-iat=604800 秒（7 天）。线上 JS 刷新逻辑将其放入 Refresh-Authorization 请求头。 |
| user.uuid | 32 字符。线上 JS 从浏览器指纹 visitorId 获取并持久化，公共请求封装放入 uuid 头。服务端是否强制绑定设备尚未验证。 |
| user.userInfo | 用户资料缓存；线上刷新逻辑读取其中 id。其存在不等于服务端认证成功。 |
| user.userStatus | 前端登录标志，不是服务端凭据。 |
| user.encryptStatus | 请求/响应加密处理开关，不是登录令牌。 |
| user.showNotice / orderSiderStatus / pwdExpired / loginFailTimes | 界面及状态控制字段，不是主要鉴权凭据。 |

其他 localStorage 键：`game.data`（页面业务状态）；`__DC_STAT_UUID`（名称呈统计标识，未证实具体用途）。未将它们认定为身份凭据。

## 证据链

1. CDP 在指定标签页读取 localStorage/sessionStorage 的字段结构，不输出值。
2. Network.getCookies 分别限定页面 URL、当前 API URL，均 cookies=[]。
3. 页面加载脚本 `/assets/index-4fe6d5d2.js` 明确配置 user store 持久化到 localStorage，路径包含上述字段。
4. 同一脚本公共请求封装含 `authorization:e.token`、`uuid:e.uuid`，以及 Device-Type 与 X-Requested-With。
5. 同一脚本刷新逻辑使用 refreshToken 与 userInfo.id，并在响应含新 token/refreshToken 时更新 store。
6. JWT 只在页面内解码头部、字段名、iat/exp；未输出签名、extend、身份信息或任何凭据全文。

## 生命周期与限制

localStorage 自身不会按 JWT 的 exp 自动删除，刷新页面/重开浏览器仍可保留；服务端是否接受由令牌有效期、撤销及可能的设备/IP 等校验决定。2 小时和 7 天是本次令牌的 exp-iat，不是剩余时长，也不是对未来所有会话的承诺。

请求头映射与刷新行为来源于当前线上 JS 静态证据；未被动抓取原始请求头，未主动触发刷新，未做删除字段的必要性对照实验。因此 uuid 是否必需、令牌撤销规则及刷新是否轮换需后续独立验证。JWT 未作密码学签名验证。

无 Cookie 不代表所有历史页面或未来场景都无 Cookie；结论限定本次页面和 API URL 的当前状态。未导出可复用登录态，凭据未落盘。
