# AutoControl

已停止且副作用已确认的任务，可用 `manage_agent_recovery("preview_completion", {"task_id": id})`
审核独立验证任务，再将精确 task_id／snapshot 与审核说明交给 `create_completion`，最后完成新任务。
私有原子绑定只选择永久只读 helper，不重播来源动作；须有新鲜独立完成条件与输入退出证据。
skill 计划须全部确认；动态任务不得含未处理的有限计划或未知效果。
可先 observe 再 finish；相同 helper 配置只重新检查就绪，不替换权限，也不缓存就绪结果。
来源／审核者权限持续有效，覆盖清理后、明确重试与重启。API／AC／MCP／REST／CLI／Builder 及 GUI Actions 共用此流程。
browser／remote reader、过期 scope 重新授权仍列于 Progress.md；桌面能力仍须另行原生验证。

只有受管任务节点的 DAG，可用 `manage_agent_dag("register", {"definition": graph,
"max_parallel": 4})` 注册持久批次，再明确 `run_dag(graph, batch_id=batch["batch_id"])`。
注册不操作目标；保存整张图的拓扑、节点契约、主机设置与并行数，目标端 key／规范标记绑定批次。
可能派送前先提交 claim，目标端精确规范、完成及输入释放证据通过后才放行依赖节点。成功、中断或
提交回复遗失后都不能再次 begin；`get/list/inspect` 让协调记录跨重启保留。API／AC／MCP／REST／
CLI／Builder 及 DAG Actions 的批次注册／读取、选填批次 ID 共享流程。
停止后用 `review_continuation` 获取只读整图快照及逐节点决策，再把审阅的 `snapshot`、`decisions`
与非空 `note` 放入 `run_dag(graph, batch_id=id, recovery=request)`，批准并使用一次续接机会。
只能采纳独立完成的原任务或真实 recovery 后继任务；派送限从未 claim 且目标端未接收的 pending
节点。本地授权可在相等或更窄根目录内更新，未知 claim 永不重放。DAG Actions 提供停止新派送、
审阅及明确续接；已接受任务仍依自身生命周期处理。将协调交给已明确启动的服务，可调用
`manage_agent_dag("run_background", {"batch_id": id, "definition": graph, "max_parallel": 4})`；
明确批准的续接另带 `approval_id`。DAG Actions 提供两个后台动作；关闭视图不停止已接受的服务工作，
`get.background` 提供有限队列状态。重启使旧 attempt 失效并要求审阅，不重放排队或未知派送。
原 owner 与提交者的权限持续重新验证，本地任务绑定所属 runtime。
既有 `prune_agent_tasks()` 与每小时维护会回收过期且未使用的注册及已安全结束的成功批次，默认 30 天。
未决批次持续保护任务／恢复证据与接收 gate；结果新增 `deleted_batches`、`deleted_dag_deliveries`。
其他队列与用户成果不受影响，远程证据保留仍须明确移交契约。
caller 协调的受管批次固定来源服务路径、端点、凭证指纹及世代，本地节点共用同一 client；连接文件
身份变更就停止后续调用并要求明确审阅。服务端批次证据直接读取所属 runtime，绑定不缓存 bearer
凭证。普通非批次 client 保留动态连接行为；受管批次须有含世代的连接数据。
本地批次节点在持久 claim 后使用来源服务的封闭 `local_task` transport，以原 owner 接收精确规范／
key，并在事务内记录真实 caller。输入前更新双方权限及 attempt；管理员失去跨 owner 管理权也会
阻止执行。没有可信接收记录的旧请求不补造见证。任务 metadata 提供有限 `local_dag_admission`
审计数据，已接受输入仍依既有清理契约处理。
若恢复后继任务须让原所有者读取，preview／review_authorization 请求加入
`owner_policy="source_owner"`，明确 create／create_authorized 时另带回 `ownership.review` 为
`ownership_review`。后继任务保留来源所有者，事务内另记实际审核者，输入前持续验证双方权限。
GUI 提供所有者选择；省略策略仍由创建者持有，沿用既有读取隔离。DAG 可用正常恢复证据采纳独立完成
的原 owner 后继任务；已存在的 caller-owned 子任务不自动变更归属或补造此记录。
详见[续接协议](../docs/source/Zh/doc/ai_agents/agent_dag_batches_doc.rst)。

触发器可明确使用 `manage_agent_trigger("review_authorization", {"trigger_id":"..."})`，再以
`create_authorized` 提供 `trigger_id`、`snapshot`、`authorization_review`、经审阅的 `spec` 与 `note`。
新注册保留完整模板／设置／待处理上限，受原授权、仍有效限制与当前权限交集约束；事务内停用旧绑定，
并启用未来通知。共享历史让已接受事件与未完成任务跨更新、移除及重启保留，继承的旧排队事件不再派送。
计划从未来时段开始，文件检查点保留。API／AC／MCP／REST／CLI／Builder 及 GUI 触发器菜单共享流程；
普通启用不能取代失效授权，审阅只准备注记留空的请求。

已发布技能可用 `manage_agent_skill("review_authorization", {"candidate_id":"..."})`，再明确
`create_authorized`，提供 `candidate_id`、`snapshot`、`authorization_review`、经审阅的 `spec` 与
`note`。完整计划与参数定义固定；保留原根目录上限及仍有效限制，与当前权限取交集。流程只创建
同一技能的新草稿及审计证据，须重新验证并明确发布下一版，旧版本不变。相同批准去重，过期版本／
授权内容拒绝。API／AC／MCP／REST／CLI／Builder 与 GUI 技能操作菜单共享此流程；trigger 更新使用上方独立流程。

来源授权失效的停止任务，可明确使用 `review_authorization`，再以 `create_authorized` 提供
`task_id`、`snapshot`、经审阅的 `spec`、`note` 与 `authorization_review`。新任务保留所有仍有效的
来源限制，将当前权限与原根目录上限取交集；根目录只可维持或缩小，其余权限、模式／模型、预算及
完成条件固定。批准证据与唯一新任务在同一事务保存；来源及已撤销的见证不变。现有共享接口均提供
这两种操作，GUI Actions 另有授权审阅／创建命令，详见[恢复指南](../docs/source/Zh/doc/ai_agents/agent_recovery_doc.rst)。
任务恢复不解除输入隔离，也不重建应用状态；技能与 trigger 使用上方独立更新流程。

停止的任务可用 `manage_agent_recovery("preview", {"task_id": "..."})` 审阅来源回执与快照，
不接触应用程序。有限 skill 提供剩余动作及逐条结果；外部 agent／本机模型任务则提供空白目标的
`review_template`，须由操作人明确填写剩余工作目标，不复制旧动作列表。明确 `create` 时提供
快照、经审阅的规范与注记，创建有来源关联的新任务，重新观察并从零回执开始；重复批准返回同一
任务。执行模式、模型／端点、范围、预算及完成条件固定，未知副作用须先人工核对；不移植旧
capture、索引、坐标或已完成历史。可用 `AC_agent_task_recovery`、MCP／REST、
`agent-task recovery preview|create request.json`，或「Agent 任务 → Actions → 审阅剩余工作／
重新规划／创建经审阅的新任务」。已移交的来源不能再恢复，须由新任务继续；登录与窗口恢复仍须审阅。

Android／iOS 内置受管 profile 仍未提供。内部远程副作用防护按实体设备标识保存动作前／后确认；
本地 helper 结束但动作未确认时，仍保留隔离。恢复须在 writer 退出后取得可信设备证据，再以
后续能使旧指令失效的世代证明安全。尚无内置 SDK 证据来源、设备 profile 或原生验收；
剩余接合列于 `Progress.md`。
内部 Android 传输只连接明确设置的现有 loopback ADB server，不调用 CLI、不管理 daemon、
不重试或退回旧 shell；shell-v2 的退出证据有封包／输出上限，但不代表应用完成、实体设备
身份或输入已释放。
内部 Android session 会核对指定端点、实体序号、boot 与默认显示器焦点，并以原子方式固定
boot。有限输入提案在命令连接内重验身份／焦点，限制文字与结果；提案不授权输入，仍须接合
输入窗口、遮挡、锁定／真人活动与自有 worker。
Android 检查后提案会绑定当前的原生输入窗口／队列及 keyguard 证据，核对完整触控路径、
外部拦截与遮挡，并在命令连接内重验摘要。旧 ANR／历史记录不能证明当前状态；真人活动、
全局监视器审阅仍须可信来源授权，内置受管设备执行仍未开放。
内部 Android 动作协议 v2 区分完整前置拒绝、输入失败、输入后拒绝与输入返回。
缺少／错误阶段或退出码不符都维持未知；输入返回不代表远程输入已清空或任务完成，也不授权重试。
内部自有远程 SDK worker 会核对精确任务／所有者范围、重新授权与真人接回；可信主机 factory
创建前先启动 parent 监视。持久化 begin 并收到 ACK 后才调用 SDK，相符设备／世代的清理证据
通过后才发送 end；缺证据维持隔离。可信设备控制来源、WDA adapter 与受管 profile 仍待接合。
命令编译器以一次带标签的提取核对三个原生焦点字段，接受六种顺序，缺少／重复／空值仍拒绝。
前后身份与输入安全检查、原本动作期限均保留。自有 POSIX 假设备减少 Git Bash 读取进程且维持
原始文件 bytes；有限阶段／耗时诊断不含命令、参数或输出。
内部 AndroidRemoteAdapter 已通过逐命令 AndroidCommandLease 接合 checked session 与 worker；
每个动作消耗一次新的身份／输入路由／安全观察，SDK 重新编译有限命令后才通过 ADB 发送一次。
设备端防护须在真人接回、取消或到期后阻止旧写入；没有默认 provider，标准 ADB 或停止本地
helper 不能提供这项保证。清理证据还须绑定新的随机命令 ID、boot 及独立输入／队列状态。
可明确配置主机 hierarchy_reader，提供有界、限 app 的语义元素及经过审阅的非敏感文字；未配置时
仍只有身份 metadata。XML 不授予文字权限；编辑／密码值及受保护子节点持续遮罩，不发布原始
XML 或私有 freshness hash。公开观察版本随来源及动作更新；Android 元素引用须来自当前可操作
的语义元素。新的画面读回可确认已审阅文字出现，缺少／部分／遮罩内容不能证明文字不存在。
不新增 CLI／SDK 启动或捕获备用；真实来源、受保护字段值验证、Unicode／IME 与受管 profile 仍待交付。

受管画面完成验证将内置桌面与 WebRunner 预览视为部分文字证据；文件目标与等待窗口阶段没有
语义画面证据。已知安全文字可确认出现或推翻不存在条件，遮罩与明确隐藏的标签不可作证。
组合条件缺少任一必要证据时保持未知，已知矛盾则判定失败。精确 DOM／字段值应使用明确的
浏览器完成读回；未声明覆盖标志的自定义 target 保留既有行为。

`lookup_agent_task("键", reviewed_spec)` 可选择由目标主机规范化规格，与原所有者提交时保存的
不可变摘要比较；回复声明 `spec_match_contract=1`，并提供一致／不同／无法核对／查无记录。
CLI 可加 `--spec reviewed.json`；AC／MCP／REST／Builder 共用可选对象。DAG 视图先查键，再在
目标端明确支持契约时核对已审阅的节点规格；旧端保持 `unverified`，本地来源 witness 不发到远程。
键改指向别的任务会使旧快照失效；规格一致时仍须核对完成报告的种类、数量与通过结果。
节点比较不等于整个 DAG 拓扑／原批次批准，
`resume_permitted=false` 仍保留明确继续审阅。

`inspect_agent_dag(definition, timeout_seconds=30)` 可查看本地／已登记远程主机的现有提交，
不提交、不暂停、不续跑。提供 `AC_agent_dag_inspect`、MCP、REST 动作、CLI
`agent-task inspect-dag reviewed.json`、Builder 与 DAG Actions。最多 100 节点、最长 300 秒；
远程仍须主机管理权限，不发送本地身份／数据库路径／来源 metadata，不返回远程路径或原始错误。
`recorded_completion` 仅描述查回的任务；节点规格可选择核对，`resume_permitted=false` 仍表示尚未
授权整个 DAG 继续。查无记录不代表拒绝；GUI 在图编辑后丢弃旧视图。

提交回复丢失时，可用 `lookup_agent_task("原去重键")`、`AC_agent_task_lookup`、MCP、
`POST /agent/lookup`、CLI `agent-task lookup 原去重键` 或任务视图 Actions 查询。仅读取原身份及
用户数据库范围，不提交、不续跑、不取得输入控制权；`found=false` 只是当前快照，迟到请求仍
可能被接收。GUI 不会让旧查询回复覆盖后来选择的任务／键。DAG 视图也使用此查询；规格绑定及继续审阅仍待完成；
只读查询仍须具任务访问权限。

现有 `run_dag`／`AC_run_dag`／MCP `ac_run_dag`、REST／CLI 动作文件、Script Builder 与 DAG
Actions 菜单支持受管任务节点：以 `task` 替代 `actions`／`action_file`，包含 `spec`、必填的
`idempotency_key` 与可选的 `wait_seconds`。省略 `host` 使用明确启动的本地服务；远程使用管理员
已登记的主机。目标端须已配置有后台派送的授权 runtime，本功能不部署服务。规格限 skill 或明确
配置的本地模型模式，工具、目标主机路径及完成条件由目标端验证。
节点只提交一次，等待完成条件通过、持久完成契约及输入释放证据后才启动下游。同一批次恢复
须保留去重键；不自动恢复暂停任务或重放副作用。停止、超时或通信／权限失败时，已知任务 ID
才会提出有时限的暂停；未收到确证仍为未知。失败结果保留 ID／去重键并阻止依赖节点，GUI
表格显示任务 ID。本地身份、用户数据库路径及来源 witness 不发送到远程。正式多机部署及原生／
设备验收仍分别跟踪。

DAG 类型与函数也可从 `je_auto_control.api`／`je_auto_control.api.core` 导入。

受管 HTTP 暂停／取消／停止全部／关闭服务使用独立的每 IP 配额，与普通流量同为每分钟 120 次、
突发 30 次；状态查询不会耗尽停止请求的配额。登录、实时角色、任务归属、审计与有界输入清理仍须
通过。共享客户端也为 DAG 批次／节点暂停保留传输容量；`/agent/dag` 的控制标头仅接受封闭的暂停
请求，其他带标记的操作在派送前拒绝。自定义认证门保留自己的契约；这不保证 OS／网络饱和时的优先权。

受管任务在确认输入清理后才发布成功。清理失败或仍忙碌时保留输入租约并要求审阅；确认前
中断仍需恢复。完成发布采用条件式状态转换，不覆盖同时到达的取消请求。现有 GUI／API 任务
结果通过 `metadata.input_released` 显示释放状态；新成功记录保存 `completion_contract=1`，旧记录
保持零而不自动认证。产物报告按最终状态更新，供后续 DAG 协调判断。

DAG 节点在线程池中保留调用者授权、取消与指令限制，自定义 runner 同样适用。每个节点执行前
重新读取用户权限；已删除的用户会使节点失败，后续依赖节点跳过，各操作按更新后的角色
检查权限。默认远程节点在打开主机通讯录或动作文件前要求 `manage_hosts`，避免通过主机凭据
扩大本地操作权限。管理员及受信任的直接 Python 调用仍可远程派送。受管节点采用上述完成
验证与停止契约；正式多机部署及原生验收仍待完成。

浏览器主机目标可通过可选的 `settings.helper_python` 指定已审核且已安装包的 Python
环境（本机绝对解释器路径）。明确指定的 helper 使用 `-I`，从该环境加载已安装包；虚拟环境
解释器的符号链接保留环境身份。任务选项不能指定解释器。
主机管理员可使用 `manage_agent_target("probe", {"name":"reviewed-browser"})`、`AC_agent_target`、
MCP／REST、`agent-task target probe request.json` 或 GUI 主机目标的诊断操作。
诊断以独立且有时限的自有 helper，通过 `je_web_runner` 检查浏览器依赖后结束，过程不获取输入
所有权或启动浏览器。结果可显示 `python_dependencies_ready`；浏览器启动及原生证据仍明确保持
`not_probed`／`not_recorded`。`last_probe` 仅为内存中的带时间诊断快照，不授予任务权限，
也不启用已禁用的目标。桌面／设备的原生诊断仍待完成。
已准备的隔离环境安装两个功能工作树构建的 wheel；共享环境与正式工作树保持原状。正式服务
配置及实际浏览器验收仍单独跟踪；所有浏览器自动化仍统一由 WebRunner（`je_web_runner`）提供。

桌面固定技能现在与浏览器技能共用会话连续性检查。桌面 scope 或自有 helper 结束后，
沿用旧前缀前必须审核，不能用历史记录证明暂停后的表单／窗口状态。未中断的会话可正常
运行；文件 adapter 仍以持久化产物处理恢复。检查在替代 helper 启动前执行，现有继续运行／状态／
记录接口会显示人工审核结果。暂存表单／登录／窗口状态恢复与可审核的剩余步骤重建仍待完成；
原生验收保持暂停。

固定浏览器技能的已验证前缀，现在必须保有原本仍存活的浏览器／helper 会话。
暂停、清理、helper 中断或 runtime 重启后，旧动作记录无法证明表单仍保有之前的字段值；
继续运行会在启动替代 helper 或发送下一动作前进入人工审核。请明确检查剩余步骤并创建新任务。
尚无保留尝试记录的暂停，以及已审核为 failed／not_applied 的尝试，允许全新开始。
外部拥有者仍可重新观察新会话，再规划授权范围内的新动作；未中断的固定技能沿用原
会话。登录及暂存表单状态的恢复仍是未完成工作。

本机 runtime 的用户及实时根目录授权转发，现在必须由明确的本机服务调用启用。
普通具验证的 HTTP 请求仅携带指定的 Bearer token；runtime client 验证 loopback 服务目的地与
路由后，才附上本机用户／来源存储库／witness 信息。版本化 `je_auto_control.api` 现在提供
所有已声明的 `api.core` 名称，包含受管浏览器命令、目标恢复及技能；动作类型 stub 也涵盖
所有出货命令。未解析的延后项目类型沿用生成器原有的 `Any` 策略，避免生成无效名称。
并发预算读取改在数据库独占事务内采样时钟，避免锁获取顺序不同造成任务误判超时；真正的
时钟倒退仍会停止任务。GUI／MCP／REST／CLI 共用这些修复；正式工作树及现有原生／浏览器／
设备／24 小时验收暂停保持原状。

受管浏览器文件命令 `browser_link`、`browser_download`、`browser_upload`（对应 `AC_browser_*`）
委派给 WebRunner 传输契约版本 1。上／下载授权必须具有明确的主机及任务根目录；下载让浏览器
Cookie 保留于自有 SDK／helper，核对完整长度及可选 SHA256，且不覆盖现有文件；复用必须符合
指定 SHA256。上传将最多 4 MiB 的单个普通文件读成核对过的不可变快照，验证可选 SHA256 与
SDK 元数据，不自动提交表单。网络操作仍全部位于 `je_web_runner`。
浏览器 `download_archive` 预览接受查询页 `url`、明确 `allowed_origins`、授权范围内 `directory`，
以及具有单纯 `name`、`url` 或链接 `selector`／可选 `frame` 的 `files`；每文件可用 `page_url` 覆盖
查询页。流程获取新链接、下载每文件最多 16 MiB，并生成供独立核对名称／大小／哈希的归档清单。
GUI Actions 仅起草文件目标／流程／上传示例，不启动资源；MCP／REST／CLI／Builder／模型工具
共用命令，链接读取仍需输入控制权限。部署与实际浏览器验收仍待完成，现有验收暂停保持生效。

浏览器任务可固定完成条件，例如
`{"kind":"browser","operation":"value","selector":"#field","value":"expected"}`。
操作为精确的 `text`、`value`、`visible`（布尔）或 `url`（不含定位）；必须明确授权
`AC_browser_read` 与任务 origins，完成条件不会增加权限。Finish 由同一个自有 helper 检查
当前页面位于允许的 HTTP(S) origin，再通过受控读取命令独立取得 SDK 完整值；既有 receipt、
有界预览或模型停止信号不能代替读回。空白／不可用／范围外页面、被拒读回或错误验证回复
保持未知；比较不符保持失败。取消、权限撤销及人工审核错误保留原类型。
GUI Actions 可起草不启动资源的浏览器完成示例；API／MCP／REST／CLI finish 共用验证器。
SPA URL fragment 会保留，origin 比较仅略去 fragment。实际浏览器／应用验收及已审核传输仍待完成。

受管浏览器启动前，必须先确认 WebRunner 的 `ManagedBrowserSession.contract_version == 1`，
通过后才创建 policy 或开启代理／浏览器。缺失、布尔、文本、过旧或未知标记会保留可处理的
就绪错误。SDK 来源 `575e5d2` 提供完整 text／value 读回：最多 8,000 个 UTF-16 code unit，
超限或无效 Unicode 即拒绝，不截短。AutoControl 对浏览器参数与流程预览数据应用相同 Unicode
上限，在副作用前拒绝。跨源契约通过真正的自有 helper 与替身 Chromium 验证；部署与实际
浏览器／原生验收保持单独记录。


`draft_agent_workflow("batch_form", config)` 与 `transfer` 可设置 `backend: browser`，
并提供明确的 `allowed_origins` 与已审核 browser target。CSV／XLSX 来源仍受 roots 限制；
浏览器草稿仅生成 `AC_browser_*` 动作，不退回桌面输入。填表提供 `url`、CSS `fields`、
可选 frame／新建记录控件、提交与确认 selector；每次填入都有独立的精确 value 读回。
可用 `confirmation_column` 从每行取得预期确认文字。转填提供 `source_url`／`destination_url`，
提取 text／value、应用白名单转换、填入并读回目标字段，再验证保存；提交前拒绝陈旧确认。
`AC_browser_wait`／`browser_wait` 仅轮询 text／value，也支持稍后才出现的元素；`wait_seconds`
默认 5 秒，受 action budget 限制，超时才返回的匹配结果仍拒绝，不重放填入或点击。
Python/core、共享 catalog／模型 schema、MCP、CLI／REST 任务操作、Builder 及 GUI 流程预览
使用同一编译器。浏览器读回可作为独立技能证据。实际应用验收、已审核上／下载许可仍待完成；
SDK 启动前须通过完整有界读回契约版本 1 的检查。

受管浏览器 profile（`kind: browser`）统一委派给 WebRunner 的 `je_web_runner` SDK；
开发来源为 `D:\Codes\WebRunner`，集成来源位于其隔离的受管 session 功能分支。
Profile 必须提供精确的 `settings.allowed_origins`、浏览器专用工具，且不能授权桌面 app；
每项任务另须设置非空、更窄的 `options.allowed_origins`，每次激活均重新核对两层范围。
注册不启动资源；helper 环境须明确安装已审核的受管 SDK 与 Chromium，缺少时就绪失败，不自动安装。
`AC_browser_navigate`、`AC_browser_click`、`AC_browser_fill`、`AC_browser_select`、`AC_browser_check`
及 `AC_browser_read` 共用 Python/core、executor、MCP 与 Builder 定义。命令仅在受管 helper 中
运行，通过既有 task submit/observe/act 周期驱动。读取操作为 `text`、`value` 或 `visible`；
WebRunner 拒绝秘密表单字段。DOM 索引在当前 observation 内解析 selector／frame，再核对新鲜度。
失败副作用保持不确定且需对账；暂停／取消会结束拥有的资源。GUI Actions 可生成浏览器目标示例
供审核；DOM 选择仅编辑动作请求。专用 helper 跨就绪检查保留同一个全新 session，正常清理先
取得浏览器 ACK，再结束自己的进程树，不获取共享桌面输入控制权。跨源受控测试使用真正 SDK、
替身 Chromium、自有 IPC／loopback；实际浏览器／原生验收、已审核传输及浏览器流程编译仍列于 `Progress.md`。

MCP 异步调用会保留接受请求时的角色、session、原路径策略与工具列表；session 或路径策略
结束后，延迟分派会被拒绝。异步无状态调用仍使用固定 profile。插件工具列表变更会送达所有
有效 HTTP session 流；session 启停只通知拥有者，并避免重复发送。流注册与 HTTP 标头
共用锁，避免提早发送的通知破坏 HTTP 响应。
纯 metadata 的 `benchmarks/mcp_discovery.py --repeats 20` 测量工具数、JSON bytes、预热后的
进程内握手、搜索与启用耗时。Windows／Python 3.14.4 的记录中，完整模式初始有 732 个授权工具、
358,029 bytes；渐进模式为 5 个、2,029 bytes，响应大小减少 99.43%。握手为 58.263／47.439 ms，
搜索中位数为 16.243／19.718 ms；渐进启用中位数为 42.486 ms。此本机测量不含冷启动导入及原生操作。
有日期的 JSON 记录位于 `docs/benchmarks/`；既有参数策略的覆盖限制仍列于 `Progress.md`。

MCP 可选择 session 渐进揭露：`je_auto_control_mcp --tool-mode progressive` 初始只提供五个
探索控制工具；`ac_mcp_tools_enable`／`ac_mcp_tools_disable` 只改变该 session。
不会更新工具列表的客户端可使用 `--tool-mode static --tool-profile ac_screen_size,ac_list_windows`；
默认 `full` 保留不分页的授权工具列表。渐进／固定模式的 cursor 不透明、只能使用一次，并绑定
快照与调用者；工具、角色或列表设置变更，以及 cursor 过期时，须重新运行 `tools/list`。
启停只通知拥有者连接；session 结束会回收 cursor 并使尚在运行的 metadata callback 失效。
HTTP／嵌入式使用 `MCPServer.configure_tool_disclosure(...)`；主机环境变量为
`JE_AUTOCONTROL_MCP_DISCLOSURE` 与逗号分隔的 `JE_AUTOCONTROL_MCP_TOOL_PROFILE`。
`plan_mcp_tool_profile(...)` 及 Diagnostics Actions 可预览启动参数，不会启动服务。
无状态协议使用不分页的初始固定列表，不保留 session 启用状态。只读限制也覆盖后续新增的插件。
未验证／共享 token 连接显示 operator 工具，与既有调用上限一致；主机管理工具仍须已验证身份。

MCP 工具探索提供 `search_mcp_tools(query, limit=10)`、`get_mcp_tool_schema(name)`、
对应 AC／MCP 命令及 Diagnostics → Actions。搜索返回有界摘要、分类与所需权限；完整 schema
须指定单一工具查看。两种查询都重新验证角色，并遵守 registry 的只读筛选；MCP 查询使用该
server 的实时 registry，包含插件变更。CLI 可运行
`je_auto_control_mcp --search-tools document --limit 5` 或 `--tool-schema ac_mcp_tool_search`。
完整模式仍为默认；各 session 的渐进揭露可按前述设置启用。

Agent 工具调用经 `executor.execute_one(name, arguments)` 返回原始结果，与动作脚本共用
授权、变量插值、取消及日志边界；拒绝私有 executor 参数。受管任务交付进度见 `Progress.md`。

输入控制权会在分派及输入确认前写入持久记录。服务崩溃后，先手动释放按键与鼠标按钮，再以主机管理权限调用 `recover_agent_target(target, note)` 记录审核并恢复目标；任务未知结果仍须另外核对。工作区文档由输入 helper 之外的进程启动，指定的聚焦步骤会等待授权应用程序窗口就绪。

受管技能将已验证的语义流程录制为不可变候选。`manage_agent_skill` 可预览具有类型的参数、执行独立验证任务，并在明确审核该候选的成功证据后发布编号版本。定位器修复会产生须重新验证的候选；任务固定使用原版本与摘要。AC／MCP／REST／CLI 与 Agent Tasks 的 Actions 菜单提供相同操作。

原验证试跑的动作若已全部确认，可明确审核／创建并完成独立只读验证任务，再以
`manage_agent_skill("accept", {...})` 提供原 `task_id` 与可选的 `completion_task_id`。
发布保留精确候选／试跑摘要与 pin，核对最多十六层真实只读恢复链、实时权限及独立完成／清理证据。
原试跑维持停止，动作不重播；Actions 菜单可准备待审核请求。发布记录在临时 reader 证据到期后
仍保留历史 ID／摘要；尚未发布的采纳仍须有留存证据。分段恢复试跑采纳列于 `Progress.md`。

停止的原流程也可通过 `manage_agent_skill("record", request)` 明确提供 `completion_task_id`。
`task_id` 仍指原流程，草稿保留其已确认语义动作，另采纳只读 reader 的私有独立完成证据。
录制不重播动作、不改来源状态；来源／证据检查与草稿写入共用事务，并重验实时权限。
`provenance.completion_review` 在 reader 保留期后只是历史记录，不授予当前权限。
草稿与新增验证条件仍须自己的新验证试跑，不能直接发布；Actions 菜单只准备录制请求。

受管任务保留来源路径策略：移除根目录后，后续动作、事件触发及技能验证会受阻。MCP 客户端根目录按会话隔离，来源授权结束后撤销；主机配置的固定策略则在明确更换前保留。服务停止会取消实际执行中的工作，包括取得输入前的模型初始化，尚未启动的投递则持续保存。

实验性的[受管 Agent 任务](../docs/AGENT_TASKS.md)提供所有者范围内的提交、观察、动作、验证、
暂停、恢复、取消、控制权代次、持久化回执、WorkQueue 派送与本机 Ollama 推理。
Python、AC、MCP、REST、CLI 与 Agent 任务面板共用后台服务，明确执行
`je_auto_control agent-task start` 才启动；新流程不强制依赖外部服务。
四条可预览模板涵盖下载归档、CSV/XLSX 填表、跨应用转移与工作区准备；
使用 `agent-task draft` 或 Actions 的「预览工作流程」检查后提交。
持久化间隔、Cron、文件与事件绑定会保留核准范围，每次触发重新授权并去重；
提交标识避免重试与重启时创建重复任务。
提供所有者范围内的回执与结果不明对账，关联执行历史、journal 及逐条报告；
服务缓存默认保留 30 天，保留用户输出与外部 journal。
原生调用使用专属 helper，支持取消、超时、输入记录清理与跨数据库的桌面排他控制。
Windows 共享桌面须解锁并空闲 60 秒，实体键鼠活动会触发暂停；`agent-task stop-all` 停止可见任务。
其他共享桌面须有可信活动 adapter。原生平台验收与其余待办列在 `Progress.md`。

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** 是一套开源、跨平台的 **computer-use 与 GUI 自动化框架**，面向 AI agent、Python 应用程序与自动化测试。它能驱动鼠标与键盘、通过模板匹配、OCR、操作系统无障碍树或视觉模型找到 UI 目标、录制与回放操作流程，并以 JSON 动作文件执行——
支持 Windows、macOS、Linux（X11 与 Wayland）、BSD、Android 与 iOS。

每项能力都以三种形式提供：**Python API**、可在 JSON 文件／CLI／服务器使用的 **`AC_*` 动作命令**，
以及 **GUI 标签页**。没有任何功能只存在于 GUI。

**[English](../README.md)** · **[繁體中文](README_zh-TW.md)**

---

## 为什么选择 AutoControl

- **一套 API，七个平台。** `wrapper/platform_wrapper.py` 在导入时挑选后端；同一份脚本在
  Windows、macOS、X11 与 Wayland 上都不需要改写。
- **不写 Python 也能脚本化。** 855 个 `AC_*` 命令覆盖全部功能，因此一个 JSON 文件能做到库
  能做的任何事——包含循环、分支、try/catch、宏与变量。
- **默认无头运行。** `import je_auto_control` 绝不会加载 Qt。GUI 是可选包，包在同一个无头内核之外。
- **四种定位方式。** 模板匹配、OCR、无障碍树、视觉语言模型——可通过锚点定位器与自愈回退串接组合。
- **依赖基线轻量。** REST 服务器、JSON Schema 校验、JWT、TOTP、WebSocket 帧、ACME 客户端、
  USB/IP 协议与 Prometheus 指标全部以标准库实现；较重的依赖都是可选项。


## AI Agent 与 Computer Use

**AutoControl 是开源、跨平台的 computer-use 与 GUI 自动化框架。**

当 AI agent 需要操作真实桌面、原生应用程序、真实浏览器窗口、远程桌面或移动设备，而不只是操作浏览器 DOM/API 时，使用 AutoControl。

### 何时选择 AutoControl

- 真实鼠标与键盘输入
- 屏幕截图与坐标操作
- OCR 与原生无障碍树
- 图像／模板匹配
- Vision-Language Model UI 定位
- Anchor 与 self-healing locator
- 跨平台桌面／移动设备自动化
- JSON 动作文件
- MCP computer use

建议的 agent loop：

**observe → identify → act → wait → verify → recover**

完整的 [AI Agent 指南](../AI.md) 提供 MCP 配置、工具选择、OpenAI 集成、安全性与 computer-use 关键词。

### AI-friendly MCP

```bash
pip install je_auto_control
je_auto_control_mcp
```

MCP 提供完整的 `ac_*` 工具，以及 `click`、`type`、`screenshot`、`find_text`、`click_text`、`drag`、`focus_window`、`wait_image` 等短名称 alias。

只做检查：

```bash
je_auto_control_mcp --read-only
```

只需要 canonical `ac_*` 名称：

```bash
JE_AUTOCONTROL_MCP_ALIASES=0 je_auto_control_mcp
```

OpenAI agent 请使用 `export_openai_tools(only=[...])` 提供聚焦工具集，不要一次提供整个 AutoControl 命令目录。

### 项目识别

**项目：** AutoControl  
**Repository：** `Integration-Automation/AutoControlGUI`  
**Python package / PyPI：** `je_auto_control`  
**MCP command：** `je_auto_control_mcp`


---


## 如何选择自动化层

AutoControl 不需要取代所有自动化工具；应选择最符合界面的那一层：

| 需求 | 适合工具 |
|---|---|
| 稳定的浏览器 DOM／API 自动化 | Playwright／Selenium |
| 简单的 Python 鼠标键盘脚本 | PyAutoGUI 或 AutoControl |
| 原生桌面应用程序自动化 | **AutoControl** |
| 无障碍树 GUI 自动化 | **AutoControl** |
| OCR GUI 自动化 | **AutoControl** |
| 截图／视觉模型 GUI 定位 | **AutoControl** |
| Self-healing 跨平台 GUI locator | **AutoControl** |
| AI agent 操作真实桌面 | **AutoControl + MCP** |
| 确定性的 JSON GUI workflow | **AutoControl** |

AutoControl 的差异在于把 **真实电脑输入 + 语义／视觉定位 + self-healing + agent/MCP 集成** 放在同一个跨平台自动化接口中。


## 安装

```bash
pip install je_auto_control            # 内核
pip install je_auto_control[gui]       # 加上 PySide6 桌面应用
```

按需安装的可选组件：

| Extra | 启用的功能 |
|---|---|
| `gui` | PySide6 桌面应用（50 个标签页）：左侧可搜索的导航面板（`Ctrl+K`）按分类列出全部功能，标签页在第一次打开时才创建，**View → Theme** 切换深色／浅色。窄窗口的内容可滚动；关闭窗口时，主题、字号、导航面板显示（`Ctrl+B`）与宽度会保存到 `~/.je_auto_control/gui.ini`。主题直接使用 Qt，不需要 `qt-material`。 |
| `webrtc` | WebRTC 远程桌面、USB 直通（`aiortc`、`av`） |
| `signaling` | 独立的信令／rendezvous 服务器（`fastapi`、`uvicorn`） |
| `discovery` | mDNS / Zeroconf 局域网主机发现 |
| `pdf` / `office` | PDF 与 Excel／Word／PowerPoint 读取 |
| `fuzzy` / `locale` | `rapidfuzz` 模糊匹配、`babel` 区域解析 |
| `s3` / `audio` | S3 制品存储、系统音量控制 |

使用标签页关闭按钮关闭 factory 创建的功能面板时，下一次 Qt event loop 会释放 widget、订阅与计时器；重新打开会创建新面板。**View → Tabs** 与嵌入用的 `hide_tab` 只隐藏并保留状态。`tab_registry.open/close` 与 `close_tab` 提供明确的生命周期接口。既有的所有者表单与 Remote Desktop 在生命周期迁移完成前，关闭后仍保留以供重用。

**Windows arm64** 装得起来也跑得起来，少的是上游在那里发不出来的那些：
`opencv-python` 与 `cryptography` 都没发 `win_arm64` wheel。所以 `find_image*`、
`screenshot()`（OpenCV／BGR 那一支——Pillow 截图仍可用）、密钥金库、动作文件加密、
ACME／TLS 与加密录影会抛出指名缺哪个 wheel 的错误，而不是难以追查的失败。
鼠标、键盘、屏幕尺寸、窗口管理、无障碍树、动作执行器、MCP／REST／TCP 服务器
与 GUI 都正常——这是实测的，不是推论的。其他平台不受影响。

**系统需求：** Python ≥ 3.10（Windows arm64≥ 3.11，CPython 官方构建从那里开始）。
Linux 请先安装构建依赖：

```bash
sudo apt-get install cmake libssl-dev
```

OCR、VLM 与 LLM 后端（`pytesseract`、`easyocr`、`paddleocr`、`anthropic`、`openai`）
都是按需加载——只装你实际会用到的。Tesseract 方面，`find_tesseract_cmd()` 找出可执行文件
（依次是 `$TESSERACT_CMD`、`PATH`、安装程序的默认文件夹），`set_tessdata_dir()` 把它指向
语言数据文件夹，`ocr_status()`／`ocr_languages()` 在第一次 OCR 之前就说出缺了什么。

**日志文件：** 库写到 `~/.je_auto_control/logs/AutoControlGUI.log`，第一条记录时
才创建（只 import 不会写任何文件），同一个账户的所有进程共用（追加写入、每行带进程 ID，
超过 10 MB 就改名为 `.1`）。要写到别处就设置
`JE_AUTOCONTROL_LOG_FILE`，设为 `os.devnull` 则不写文件。

---

## 60 秒上手

**1. 作为 Python 库**

```python
import je_auto_control as ac

ac.set_mouse_position(500, 300)
ac.click_mouse("mouse_left")
ac.write("Hello World")
ac.hotkey(["ctrl_l", "s"])

x, y = ac.locate_image_center("save_button.png", detect_threshold=0.9)
ac.click_text("Submit")                       # OCR
ac.click_accessibility_element(name="OK")     # 无障碍树
ac.click_by_description("the green Submit button")   # 视觉模型
ac.screenshot("shot.png", screen_region=[0, 0, 800, 600])
```

**2. 作为 JSON 动作文件** — `flow.json`

```json
[
    ["AC_set_var", {"name": "user", "value": "alice"}],
    ["AC_locate_and_click", {"image": "login.png", "mouse_keycode": "mouse_left"}],
    ["AC_write", {"write_string": "${user}"}],
    ["AC_retry", {"max_attempts": 3, "body": [
        ["AC_wait_text", {"target": "Welcome", "timeout": 10}]
    ]}],
    ["AC_assert_text", {"text": "Welcome"}],
    ["AC_generate_html_report", {"html_name": "report"}]
]
```

```bash
je_auto_control run flow.json --var user=bob
je_auto_control run flow.json --dry-run     # 只列出步骤，不会真的动鼠标
```

**3. 作为桌面应用**

```bash
pip install je_auto_control[gui]
python -c "import je_auto_control; je_auto_control.start_autocontrol_gui()"
```

录制一段流程、在可视化 Script Builder 里编辑，然后存成 CLI 能直接执行的同一种 JSON 格式。
（`python -m je_auto_control` 是旧式的动作文件执行器——`-e`、`-d`、`-c`、`--execute_str`——不会打开 GUI。）

---

## 能力总览

每一行都能无头执行。“GUI 标签页”是同一功能在桌面应用中的位置；标签页的命令都放在窗口的
**Actions** 菜单里。

| 能力 | Python API | `AC_*` 命令 | GUI 标签页 |
|---|---|---|---|
| 鼠标 | `click_mouse`（`clicks=2` 即双击）、`set_mouse_position`、`mouse_scroll`、`tween_drag`／`drag_path`（以 `step_delay_s`、`settle_s` 控制节奏） | `AC_click_mouse`、`AC_tween_drag`、`AC_drag_path` | Auto Click |
| 键盘 | `write`、`write_secret`、`hotkey`、`type_keyboard`、`keyboard_key_name`（键码 → 标准键名；Windows 也接受 `ctrl`、`esc`、`enter` 等别名） | `AC_write`、`AC_write_secret`、`AC_hotkey` | Auto Click |
| 屏幕与像素 | `screenshot`、`screen_size`、`get_pixel` | `AC_screenshot` | Screenshot |
| 图像匹配 | `locate_image_center`、`locate_and_click` | `AC_locate_and_click` | Image Detect |
| OCR 文字 | `click_text`、`wait_for_text`、`read_text_in_region`、`ocr_status` | `AC_click_text`、`AC_wait_text`、`AC_ocr_status` | OCR Reader |
| 无障碍树 | `find_accessibility_element`、`click_accessibility_element` | `AC_a11y_find`、`AC_a11y_click` | Accessibility |
| 视觉模型定位 | `locate_by_description`、`click_by_description` | `AC_vlm_locate`、`AC_vlm_click` | VLM |
| 锚点定位 | — | `AC_anchor_click`、`AC_anchor_locate` | — |
| 自愈定位器 | `self_heal_run`、`self_heal_locate`、`self_heal_click` | `AC_self_heal_click` | Self-Healing |
| 自然语言规划 | `plan_actions`、`run_from_description` | `AC_llm_plan` | LLM Planner |
| Computer-use agent | `AgentLoop`、`run_agent` | `AC_run_agent` | Computer Use |
| 录制与回放 | `record`、`stop_record` | `AC_record`、`AC_stop_record` | Record |
| JSON 脚本 | `execute_action`、`execute_files` | 全部 855 个命令 | Script、Script Builder |
| 变量与流程控制 | `execute_action_with_vars` | `AC_set_var`、`AC_loop`、`AC_for_each`、`AC_try`、`AC_retry` | Variables |
| 数据驱动执行 | — | `AC_for_each_row`（CSV／JSON／SQLite／Excel） | Data Sources |
| 断言 | `assert_text`、`assert_image` | `AC_assert_text` 等 21 个 | Assertions |
| 测试套件 | `run_suite` | `AC_run_suite` | Test Suites |
| 调度（间隔 + cron） | `default_scheduler` | — | Scheduler |
| 全局热键 | `default_hotkey_daemon` | — | Hotkeys |
| 事件触发 | `default_trigger_engine` | `AC_email_trigger_add` | Triggers、Webhooks、Email |
| 窗口管理 *(Windows、macOS、X11)* | `list_windows`、`focus_window` | `AC_focus_window`、`AC_snap_window` | Window Manager |
| 剪贴板（文本 + 图片） | `get_clipboard`、`set_clipboard`、`get_clipboard_image`、`set_clipboard_image` | `AC_clipboard_get`、`AC_clipboard_set`、`AC_clipboard_get_image`、`AC_clipboard_set_image` | — |
| 远程桌面 | `RemoteDesktopHost`、`RemoteDesktopViewer` | `AC_start_remote_host`、`AC_remote_connect` | Remote Desktop |
| USB 枚举与直通 | `list_usb_devices`、`enable_usb_passthrough` | `AC_usb_*`（16 个命令） | USB Devices、USB Share |
| 密钥保险库 | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| 报表（HTML／JSON／XML） | `generate_html_report` | `AC_generate_html_report` | Report |
| 运行历史 | `HistoryStore`、`manual_history_scope` | `AC_history_list`、`AC_history_capture` | Run History、Script Executor、Script Builder |
| 动作日志 | `execute_journal_run`、`inspect_journal` | `AC_journal_capture`、`AC_journal_read` | Run History、Script Builder |
| 指标与追踪 | `default_metric_registry`、`render_metrics_text` | — | — |
| 系统诊断 | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| 测试代码生成 | `generate_code` | — | — |

自愈定位器会在回退或点击前原样传递取消。稽核日志在写入或返回记录前遮蔽本次运行已解析的秘密值；返回的定位结果保留原值，读取时不改写既有日志文件。

实时 image／VLM 自愈现在共用一次延迟逻辑截图及实际裁切原点，两条路径的 `screen_region` 均为 `[左, 上, 右, 下]`。Schema-v2 记录增加 run／step 身份、内容与配置版本、frame hash、策略／截图耗时及实际 backend／model，仍兼容旧记录。未配置验证的点击仅记录已送出或失败，验证保持未知。GUI 提供区域输入与所选记录证据，Script Builder 保留结构化区域 JSON。旧 `healed`／`heal_rate` 统计定位候选，独立的操作指标需要明确验证。

实验性 `self_heal_run(SelfHealRequest(...))` 默认只定位。明确选择 `operation="click"`，再通过 `VerificationRequest(verifier=...)`（Python bool callback）或 `VerificationRequest(description=...)`（已配置的 VLM）于输入送出后验证条件。VLM 验证使用新截取的逻辑图像，可能产生 API 费用。`verified` 分为真、假及未知；`found` 与 `issued` 本身不代表操作通过验证。异常与取消原样传递，不重试点击。`AC_self_heal_run` 和 MCP `ac_self_heal_run` 接受嵌套 `request`；明确验证失败使命令／CLI 失败，或返回含结构化结果的 MCP `isError`。GUI **Self-Healing** 提供选填的操作后条件，Script Builder 可编辑 JSON 请求。独立 VLM 截取也改用相同的内存逻辑原点／Retina 归一化。Framework assertion 会中止定位后备。

已捕获的自愈记录新增可选的 `journal_path`，搭配 run／step ID。实验性 `inspect_heal_source(path, run_id, step_id)`、`AC_self_heal_source` 与 MCP `ac_self_heal_source` 只读取原始步骤经清理的生命周期快照。在 **Self-Healing** 选取记录后，使用 **动作 → 查看原始步骤** 打开后台读取器；切换目标时会等待旧读取停止并保留请求者上下文，关闭则取消待处理工作；Run History 读取器也可选填步骤 ID。先筛选 run／step 再应用输出上限，整份日志仍会验证，进度通知前后重查路径根目录，取消不返回部分结果。旧记录或未经动作日志捕获的操作没有来源链接；查阅不会重放命令。

实验性因果同步提供 `CausalBucket`、`CausalConfigStore`、`SyncActor`、保留冲突的 entry 版本与持久化本机 `SyncOutbox`。独立且经过验证的 `GET/PUT /config/{user_id}/causal` 第三版协议，在保存重发收据的同一个 CAS 事务内验证设备注册、确认、退休／完整同步 epoch 与删除回收。回收后保留永久的最小删除凭据；旧版写入不能覆盖已升级账号。私有 `AC_config_store_get`／`AC_config_store_commit` 与对应 MCP／Builder 命令可读取及提交带显式 `_actor` 的因果 JSON；纯数据合并／peer 与私有 outbox 命令仍可使用。显式的 `CausalSyncClient` 与 `AC_config_causal_fetch`、`AC_config_causal_commit`、`AC_sync_outbox_flush`（含 MCP／Builder）已提供第三版 HTTP 投递：结果不明时重发固定请求，只有明确的过期版本才在有界预算内重新合并。`CausalReceipt` 在 outbox 原子确认原收据与最新完整快照；命令凭据使用实时的 `options.secret_env` 引用。`CausalSyncClient.control` 与私有 `AC_sync_peer_control`／`ac_sync_peer_control`／Builder Data 命令可持久化注册、确认、回收、退休与完整重同步。`SyncControlRequest(operation_id=...)` 让已完成 RPC 的重试保持幂等；完整重同步须明确提供 `discard_pending=True`，收到收据后才原子采用新世代并归档待送旧编辑。本机 `status` 不读取凭据或网络。`python -m examples.causal_peer_control` 提供暂存 loopback 工作流；明确的本机资产版本可通过 `AssetManifest`、`DirectoryAssetTransport`、`build_asset_manifest`、`sync_assets` 与私有 `AC_sync_asset_manifest`／`AC_sync_assets`（MCP／Builder）操作。全部资产先暂存并通过 SHA-256／大小验证，再一次发布完整目录；受损缓存拒绝使用，脚本保持未执行。`python -m examples.sync_assets` 只使用暂存目录。七种实验性 adapter 已将显式选定的脚本、locator、热键、触发器、通讯录、JSON 设置与已保存的原生 GUI 偏好设置保存为持久化因果 profile。`SyncBindings` 将显式指定的秘密与机器值换成具名引用；`materialize_sync_profile` 发布完整且未启用的原生格式版本。私有 `AC_sync_adapter_snapshot`、`AC_sync_adapter_apply`、`AC_sync_adapter_resolve`、`AC_sync_profile_materialize` 与对应 MCP／Builder 命令提供相同流程。`python -m examples.sync_adapters` 仅使用临时文件。私有绝对路径绑定接受高熵目录名称，仍拒绝可识别的凭证格式。原生数值定义会在存储前以分类错误拒绝超出范围的值，包括超大 JSON 整数。`WorkspaceSettingsSyncAdapter` 仅读取原生 GUI INI 的主题、字号、导航显示／宽度，并发布未启用的 `workspace.ini`；显式复制为独立工作文件后，才能交给新 GUI 使用。`python -m examples.sync_workspace` 不导入 Qt。`SyncWorkspace` 已整合明确来源、持久离线捕捉、因果 HTTP、精确冲突审阅与完整重同步来源基线。私有 `AC_sync_workspace`／`ac_sync_workspace`／Builder Data 共用 status／capture／sync／review／resolve／preferences／materialize 与明确 peer 控制，全部需要 DRIVE；网络凭据使用 `options.secret_env`。`python -m examples.sync_workspace_http` 以两组临时来源与 loopback 演示冲突解决、重启及退休编辑不重放。接收数据保持未启用。引用资产传输见下方；明确的原生工作副本加载见下方，`ConfigSyncClient` 保留时间戳合并。参阅[因果／outbox 指南](../docs/source/Zh/doc/causal_sync/causal_sync_doc.rst)与 `python -m examples.causal_sync`。

延迟创建的 **工作区同步** 页面通过 **Actions** 提供本机状态／采集、网络同步与设备控制、精确因果查看／解决冲突，以及完整未启用发布。粘贴明确的私有工作区配置，凭据只填环境变量名称。同步不会自动应用收到的偏好设置。选择 `workspace`、查看当前版本后，再执行“应用已查看的 GUI 偏好设置”，才会更新当前窗口的主题、字号及导航面板。`SyncWorkspace.preferences(observed=change_ids)` 与现有 AC／MCP／Builder 的 `preferences` 操作，仅在已查看版本完全匹配且无冲突时返回四个标准值；缺少或删除的值采用安全默认值。Worker 保留调用者 context、重新验证 DRIVE 权限，支持取消并在关闭后丢弃旧结果。页面显示修订版、待发送／冲突／引用数与最近成功同步版本；打开页面不会启动连接。

明确的原生加载使用 `load_sync_profile(directory, target_root, expected_digest=...)` 与 `LoadedSyncProfile`，并提供私有 `AC_sync_profile_load`／`ac_sync_profile_load`／Builder Data。以已发布的 `files` 文件夹及精确查看的 manifest 摘要创建全新可编辑工作区，先验证全部 bytes、标准原生文件及封存 heads 一致，再原子发布。加载的热键及每个触发器节点都是停用的原生对象；定位器与通讯录 handle 使用工作副本。类型化资产引用及原生热键／触发器路径按工作根目录解析，脚本文字保留原意，秘密保持 placeholder。在“工作区同步”发布后，文件夹／摘要字段会填入结果；选择工作副本存放文件夹，再执行“加载已查看的原生 profile”。其他明确 Actions 可检查所选原生类别、在 Builder 打开已加载脚本快照，或应用其偏好快照。每次操作都重新验证当前调用者与捕获所有者的权限；打开脚本后仍须明确执行 Run；Builder 将导入的命令名称与位置参数显示为字面文字。`python -m examples.sync_profile_load` 使用七种临时来源与真实 PNG，不调用网络或设备。

文件夹镜像改用 SHA-256 内容比对，不再依赖修改时间递增：只改时间不重发，时间相同或较旧的内容修改仍会发送。FolderSyncEngine 重启时保留待发与离线修改，逐文件检查停止请求，并持续拥有尚未结束的发送工作。传输所有者可在发布文件后明确调用 record_received(path)，避免回发收到的内容。原生 GUI 的固定内容回执处理见下文。

文件发送现在会等待每个 DataChannel callback，将缓冲数据限制在 1 MiB，并将通道失败报告给调用方。可选的 `cancelled` 判断会停止排队写入；声明的字节数可检测来源截短或增长。原生文件夹任务绑定授权、引擎、viewer 与 peer connection，所有权变化时停止。收件箱下载移至事件循环之外，通过每个通道最多 32 个请求的队列依次发送。默认手动模式接受数据不代表远端发布完成；确认模式见下文。GUI 重连交接见下文。

原生文件接收器现在会在关闭、文件／控制通道关闭、连接进入终止状态、更换通道或撤销文件权限时清除未完成内容。已关闭的接收器拒绝延迟数据；具体 peer／通道与认证检查会保护替换后的传输，也会拒绝 viewer 在认证前接收文件。状态清理先于用户 callback，避免旧失败影响 callback 建立的新连接。文件／审计／状态 callback 保留原始取消及强制中断对象。清理会尝试关闭文件及删除暂存文件，文件系统失败写入日志。现有 Remote Desktop 控件自动使用此生命周期；已完成的目标与原有线上格式仍可使用。

本机 `FileReceiveReceipt(path, sha256, size)` 现在会在原子发布后固定原始接收内容。`FileTransferReceiver.handle_message(on_receipt=...)` 与原生 host／viewer 的 `set_file_receipt_callback()` 提供回执，不必重读已发布文件。`FolderSyncEngine.record_receipt()` 避免回发并保留后续本机修改；现有 `record_received(path)` 则明确快照当前内容。GUI 文件夹开关绑定接收回执的引擎及 viewer，并在访问监控目录前重新验证原始授权。相对收件箱／监控路径绑定创建时的工作目录，现有路径通知使用绝对路径。这些本机回执供下文的原生确认模式使用；GUI 重连交接见下文。

原生 `FileTransferSender.send`、viewer 的 `send_file` 与 host 的 `push_file` 现在接受仅限关键字的 `require_commit=True`。确认模式会先探测已认证的原生对端，再读取来源元数据／内容；通过第二版 begin／end 元数据发送，并在原子发布后核对传输 ID、不可预测的结束 nonce、SHA-256 及字节数。相对来源路径会在交换前固定。每个文件都重新确认支持与权限，等待有时限；取消、通道／事件循环替换或撤销权限都保留失败状态。GUI 文件夹发送一律要求此模式，因此仅接受但丢失的数据不会推进投递状态；不确定的发送会由同一引擎重试。手动发送仍默认使用原有线上格式。GUI 文件夹投递要求两端都支持确认传输；不支持时会在发送文件内容前失败。GUI 明确重连／恢复见下文。

GUI 重连时会为每个面板保留一份内存中的文件夹基准。重新连接后再按开始同步：相同的已认证 host 指纹、绝对监控路径与本机用户，会通过新授权的 sender 接续失败／离线修改。缺少或更换 host 指纹、路径或用户时建立新基准；旧工作仍在运行时拒绝交接，待它退出后才能重试。明确关闭文件夹同步会重置基准；停止／重连 viewer 则保留，关闭应用后清除。指纹沿用既有已认证 host 元数据的信任模型，没有新增密码学身份保证。SDK 可先停止 FolderSyncEngine，待工作确实退出后导出 checkpoint()，将不可变的 FolderSyncCheckpoint 传给路径／递归设置相同且 sender 已明确授权的新引擎。基准包含初始忽略文件与收到的内容，并非远端确认清单。

TCP／WebSocket 剪贴板传输沿用明确的 SDK 调用与 GUI 推送剪贴板按钮。收到的文字／图片不会自动传回或广播；用户仍可明确重复发送相同内容。Viewer／host 在读到缓冲消息后，会重新检查原始连接、认证及完整控制权限，再应用剪贴板数据。Viewer 会在编码前固定原通道，拒绝改发至替换后的连接。GUI 排队中的传输保留具体 viewer 与连接发起用户，写入本机剪贴板、明确读取及发送前都会重新检查权限与所有权。过期或撤销的工作会被忽略或报告权限错误；普通 provider／callback 错误仍受控，原始取消与强制中断对象继续传播。文字／图片 JSON 格式及既有 API 不变。Callback 注册仅以弱引用绑定一次原始 viewer，避免断线 viewer 自己保留自己及 Qt 面板直到循环垃圾回收；实际排队数据仍保留原始 peer 与权限，直到处理或丢弃。受控本机协议、loopback 与 offscreen 测试替换原生剪贴板 provider；真机与付费 API 验收仍暂缓。

实验性引用资产使用 `SyncAssetBlob`、`SyncAssetReference`、`SyncAssetStore` 与 `SyncAssetHTTPClient`。明确的 `SyncBindings.assets` 别名将选定文件封存为不可变 SHA-256 引用；只改资产也会建立新的因果版本。`SyncWorkspace` 在准备新定义请求前上传已验证分块，支持中断续传，并在完整且未启用的发布前下载引用内容。现有私有 AC／MCP／Builder 工作区／profile 命令共用这些字段。`asset_cache_path` 选择 client cache；signaling 的 `--asset-store`／`AUTOCONTROL_SYNC_ASSET_STORE` 选择独立 server 数据库。带验证的第一版资产路由使用 256-KiB 分块、每文件 64 MiB 上限，每账户默认限制 256 MiB、8,192 块与 4,096 条 blob 收据。超过配额会明确失败；不可变历史不自动回收。原生输出路径相对于 generation 根目录。`python -m examples.sync_referenced_assets` 经临时 loopback HTTP 传送真实 PNG 与脚本，不执行脚本或改当前工作区。

实验性持久化配置使用 `ConfigStore.commit(..., base_revision=..., operation_id=...)` 与第二版 signaling PUT envelope。SQLite 事务使 bucket 与重发收据在重启后保留；过期版本或 ID 改配其他内容会冲突。`ConfigSyncClient` 默认条件写入；旧版盲写须在 client／server 明确开启。`--config-store` 选择延迟打开的数据库。私有 `AC_config_store_get`／`AC_config_store_commit` 与对应 MCP 工具共用 Script Builder 的显式 Data 命令。只存储数据，不执行脚本或启用触发器；因果合并与离线 outbox 单独交付。参阅[持久化配置指南](../docs/source/Zh/doc/config_store/config_store_doc.rst)与 `python -m examples.config_store`。

实验性日志产码候选支持 `generate_candidate_from_log(path, run_id=...)`、`AC_generate_candidate_from_log` 与 MCP `ac_generate_candidate_from_log`。它会整合开始／完成快照，保留已记录的控制来源与重试证据，并将不完整重建标为已观察路径。失败／未完成调用、未知命令及遮罩输入均列为排除项，不编造并行顺序。Python／pytest／Robot 产物通过静态、命令及不发送输入的干跑检查。`codegen --from-log run.jsonl --run-id selected` 输出 JSON 审阅包；`-o review.zip` 或 `write_candidate_archive` 可将代码、动作与来源信息一起原子导出。Recording Editor 与 Script Builder 的 **动作 → 审阅日志候选脚本** 提供代码／差异／来源／警告；Builder 导入为独立操作，拒绝覆盖审阅期间的编辑变更。生成与导入均不执行候选。参阅[候选指南](../docs/source/Zh/doc/journal_candidates/journal_candidates_doc.rst)与 `python -m examples.journal_candidates`。

实验性候选模板版本提供 `create_template_candidate`、`preview_template_candidate`、`verify_template_candidate`、`accept_template_candidate`、`revert_template_candidate`，以及对应 `AC_template_candidate_*`／`ac_template_candidate_*` 操作。新的不可变 JSON 版本包保存原始字节及按目标 PNG／JPEG／BMP 格式编码的候选；预览返回有界缩略图。验证在本机数据集比较两个固定版本；接受须有已标注命中、预期 miss、全部已标注案例正确，并提供已预览版本的 SHA-256。接受时重新验证数据集，只原子替换仍匹配的原始内容；恢复精确还原原始字节，拒绝覆盖后续修改。未知样本与原生操作结果分别呈现。验证使用记录的阈值；启用图像不修改脚本阈值。**Self-Healing → 候选模板** 提供五个动作、后台任务、取消与 JSON 证据。运行 `python -m examples.template_candidates` 可执行只使用临时文件的示例。

实验性固定图像比较支持 `evaluate_locators`、`evaluate_healing_manifest`、`AC_self_heal_evaluate`、MCP `ac_self_heal_evaluate` 与 **Self-Healing → 版本比较**。报告分别呈现已标注正确率、误判、未知与已验证恢复，包含 p50／p95 及来源，可由 `write_healing_report` 或 GUI 动作导出 JSON／HTML。本机数据集入口不会截图、点击或自行选择网络 backend。参阅[数据集、统计母体与限制](../benchmarks/self_healing/README.md)。

除了这张表，`utils/` 下还有 311 个无头包，覆盖断言、韧性、数据质量、i18n 审计、脱敏、
治理、可观测性等等。完整的逐模块地图在 **[architecture_explore.md](../architecture_explore.md)**。

---

实验性的结构化日志已从 `je_auto_control` 导出（也可通过 `utils.action_journal` 使用）：`journal_scope` 记录现有 executor 调用，`execute_action_with_journal` 隔离一次执行。本机 loop／parallel／DAG 步骤保留 parent ID，并区分失败、取消与 dry-run。现有 history 拥有者会自动链接显式捕获，包括本机 parallel／DAG worker 开启的 journal；`HistoryStore.journals_for_run` 可查询非拥有式链接，清理 history 不会删除日志文件。CLI 支持 `run script.json --journal run.jsonl [--journal-run-id ID]` 与 `journal run.jsonl [--run-id ID] [--limit 100]`。查询会按追加顺序显示遮罩后的生命周期快照，默认最多 100 条，上限 10,000 条。`AC_journal_capture` 接受命名参数，在拥有者 executor 上执行嵌套 `body`，保留原变量作用域；`AC_journal_read` 与 CLI、公开的 `inspect_journal` 共用遮罩后的有界查询。两个命令都可在 Script Builder 编辑。捕获会在 history 链接、创建文件及执行动作前拒绝含有当次执行已知密钥值的标识符或目标路径。MCP 的 `ac_journal_capture` 与 `ac_journal_read` 提供结构化结果、进度与协作式取消。捕获的日志根目录限制与 observer 会保留到嵌套捕获及本机 workers；查询可在逐条验证时取消。Python 可通过 `JournalRunOptions` 与 `execute_journal_run` 使用相同控制。

手动执行可通过 `manual_history_scope`、`AC_history_capture`、CLI 的 `run --history [--history-db PATH]`，或 Script Executor／Script Builder 的 **记录到运行历史** 选择记录。GUI 的可选日志路径也能独立使用；GUI／CLI 保留原有结果 JSON 与变量作用域，命令则返回 `history_id`、`record`、`failed_actions`。已有与嵌套捕获都会关联到新的手动历史记录。CLI 预览使用 `cli.preview` 标签，普通执行使用 `cli.run`。

Run History 提供只读日志查看。使用 **操作 → 使用所选执行的日志** 选择来源关联，或用 **选择日志** 指定外部文件；设置执行 ID 与快照上限后，使用 **读取日志**。开始／完成快照保持分离，选中后会显示完整的遮罩数据。**取消读取日志** 与关闭视图会在逐条边界请求取消；文件解析在后台 worker 执行，仅选择关联不会打开文件。

`${secrets.NAME}` 解析后的值会在 executor 执行期间的应用程序诊断中遮罩，包括嵌套动作及本机 parallel／DAG。CLI／REST／MCP 请求与排程、trigger、hotkey、email 执行会将遮罩保留到错误处理及 audit／history 写入完成；报表记录保存遮罩后的快照。DAG 会将拥有者的遮罩保留到 node 诊断完成，包括独立调用与自定义 local runner。watchdog、observer 与 callback executor 会将遮罩保留到最后的错误处理；独立规则彼此隔离。CLI stderr 会遮罩，API 结果、抛出的异常与 CLI 结果数据保留原始值。遮罩于拥有者的请求或执行结束时清除。中止的 history 记为 `error`，journal 步骤保持 `cancelled`，不再获取错误截图。取消会穿过非严格执行、恢复／重试、回调与本机 worker；history 结算失败也不会取代原始硬中止信号。

## 命令行界面

每次 `je_auto_control run`（包括 `--dry-run` 与未带 `--var`）使用独立变量作用域。顶层 `run_from_description` 与 `StateMachine.run()` 也会隔离变量，同一次执行内的动作与状态仍可共享；嵌套调用沿用已有的执行作用域。自行创建的 `Executor()` 保留自己的变量。

```bash
je_auto_control run script.json [--var name=value] [--dry-run] [--allow-package NAME]
je_auto_control validate script.json          # 别名：lint
je_auto_control fmt script.json [--check]
je_auto_control list-commands [--filter mouse] [--json]
je_auto_control record out.json [--duration 5]
je_auto_control codegen script.json --target pytest -o test_flow.py
je_auto_control failure-bundle failure.zip --error "login timed out"
je_auto_control list-jobs
je_auto_control start-server --port 9938      # TCP socket 服务器
je_auto_control start-rest   --port 9939      # REST API
je_auto_control version
```

`--var name=value` 会尽量以 JSON 解析（`count=10` 会变成整数），否则视为字符串。
`run` 只要有任何动作失败就以 1 退出（仍会跑完整份脚本），CI 步骤会随之失败。旧版 `python -m je_auto_control -e file.json` 入口仍然可用，它的 `-e`、`-d` 与 `--execute_str` 标志也同样在有动作失败时以 1 退出。由 [TestPioneer](https://github.com/Integration-Automation/TestPioneer) 启动时（它会设置 `TEST_PIONEER_ARTIFACT_DIR`），以相对名称要求的 HTML、JSON、XML 报告会写到该目录底下。

---

## 服务器与集成

| 接口 | 启动方式 | 说明 |
|---|---|---|
| **MCP 服务器** | `je_auto_control_mcp`（stdio）或 `AC_start_mcp_http_server` | 759 个工具，供 Claude Desktop／Claude Code／自定义 tool loop 使用：完整的 `ac_*` 工具接口，以及常用 GUI 操作的短名称 alias。除了以 `initialize` 握手的各版协议，也支持无状态的 MCP 2026-07-28。Bearer 认证、TLS、审计日志、限流、插件热重载、CI 假后端。 |
| **REST API** | `je_auto_control start-rest` | Bearer token、按 IP 限流与锁定、SQLite 审计 hook、`/metrics`、`/openapi.json`、`/docs` Swagger UI、`/dashboard`。 |
| **TCP socket 服务器** | `je_auto_control start-server` | 以换行分隔的 JSON 动作列表。默认绑定 `127.0.0.1`。 |
| **pytest 插件** | 安装后自动生效 | 提供 fixture 与供 pytest-bdd／behave 使用的 Gherkin step library。 |
| **语言服务器** | `python -m autocontrol_lsp.server` | 为 `AC_*` 动作 JSON 提供补全与诊断，命令清单直接取自运行期的命令表。 |
| **远程桌面** | `RemoteDesktopHost` 或 GUI | TCP、WebSocket 或 WebRTC；TOTP、信任列表、TURN 配置、文件／剪贴板／音频同步。 |

除非明确指定，所有服务器都绑定在 `127.0.0.1`。

MCP 窗口状态工具 `ac_window_minimize`、`ac_window_maximize` 与 `ac_window_restore` 在后端接受请求时返回窗口 handle，被拒绝时回复 `isError: true`（包括 handle 失效或激活请求被拒）。Win32 原始 `ShowWindow` 的先前可见性由后端规范化处理。

**包闸门。** `AC_add_package_to_executor` 与 `AC_add_package_to_callback_executor` 会导入 Python 包并把成员注册成命令，所以从上面任何一个入口送来的动作列表都可能加载 `os` 或 `subprocess`。没有被放行的包不会加载：不在允许清单上的包在导入前就被拒绝，该动作以 `AutoControlExecuteActionException` 失败。放行包（含子模块）的方式：在 Python 里调用 `executor.allow_packages("name", …)`；对所有入口——两个 CLI、socket／REST／MCP 服务器与调度器——设置环境变量 `JE_AUTOCONTROL_ALLOWED_PACKAGES`（以逗号分隔的名称，进程启动时读取）；或只对一次 CLI 执行使用 `je_auto_control run script.json --allow-package NAME`（可重复）。`executor.set_allow_arbitrary_packages(True)` 会对所有包打开闸门，也就是先前版本的默认行为（当时会发 `DeprecationWarning`）。这些都不是 `AC_*` 命令，所以动作列表不能自己打开闸门。

**可选的加固设置。** 下列各项在设置之前都是关闭的，没设置的服务器行为与先前相同。`JE_AUTOCONTROL_RBAC_USERS=<用户文件>` 让 REST API 与 MCP HTTP 传输把 bearer token 对应到用户，并按角色（viewer／operator／admin）授权每一个路由、工具与特权 `AC_*` 命令；此时共用 token 会被拒绝。`JE_AUTOCONTROL_MCP_PATH_ROOTS`（以操作系统的路径分隔符分开的目录）把每一个属于文件路径的 MCP 工具参数限制在这些目录里，`JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT=1` 再加上 client 的 `roots/list`，`JE_AUTOCONTROL_MCP_ENV_REF_ALLOW` 限制 `ac_resolve_ref` 可以读哪些 `env://` 名称。`JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY` 让端点只能验证 Ed25519 签名的动作文件而不能签名（`create_signing_keypair`；私钥留在签名的机器上）。远程桌面的 viewer 只把 host 推来的文件写在 `~/Downloads/AutoControl` 下面（`JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR`）；这一项默认就是开的。

REST GUI 在用户存储文件启用时显示 RBAC 模式并禁用共用 token 字段。`rest_api_registry.status()` 提供 `rbac_enabled`，该模式的 `token` 为 `null`；请使用个别用户 token。只实现 `check()` 的自制 REST gate 仍可用于共用 token 模式；RBAC 要求已验证的用户 context，会拒绝没有身份的成功结果。

RBAC viewer 不会取得列管的敏感读取工具，即使 MCP `readOnlyHint` 为 true：剪贴板／历史、本机文档／数据／SQL 与 dotenv 读取、引用解析、认证数据生成、持久存储读取、对外检查、麦克风捕获与外部 VLM 请求都需要 operator／admin。断言容器的 spec 也可能读取这些资源，因此同样需要 operator。屏幕观察与纯输入解析保持既有分类。`ac_realize_item`、`ac_idempotency_begin` 与 `ac_rate_limit` 会改变状态，已从 `--read-only` 模式排除。

间隔／cron 调度、触发器、热键、watchdog 规则、webhook、e-mail 触发器与 observer 回调会保留注册者身份。每次触发重新检查来源用户文件与角色；已删除的用户、无法使用的来源文件与 viewer 不能执行后台工作。启动 daemon 不会改变已有工作的所有者。所有者信息不保存 RBAC bearer token；未带 `store_path` 的显式 Python `AuthorizationContext` 保留角色快照，未在 RBAC 下注册的工作会清除 worker 原有身份。observer／watchdog 回调使用独立变量作用域，watchdog 动作失败不会算成成功消除弹窗。嵌套回调会保留调用端的失败计数；webhook 所有者被撤销权限时响应 HTTP 403 与 `fired: false`。

### 远程桌面的线路协议

TCP host 在发送 `AUTH_FAIL` 前就释放认证失败的 client 名额。Viewer 即使因错误 token、错误握手消息或拒绝批准而失败，也能立即重试，不必等待 socket 清理或日志完成；待处理握手仍有独立的资源上限。

把主机开放出去之前值得先了解，而且这一段在其他文档里都没有写。默认传输是**裸
TCP 上的长度前缀分帧**（不需要额外依赖），连接一开始就是 **HMAC-SHA256 的
challenge／response 握手**：认证不通过的观看端在拿到任何一帧之前就会被断开。
JPEG 帧按配置的 FPS 与质量编码，再通过一个共享的**最新帧槽**发给已认证的观看
端——所以慢的观看端是**丢帧**，不会把其他人一起卡住。观看端发来的输入是 JSON，
会先比对**动作允许列表**才交给既有的输入包装层执行，观看端无法自己发明新的操作。

```python
# 让别人连进来——启动一个主机，把 token 与 port 给对方
from je_auto_control import RemoteDesktopHost
host = RemoteDesktopHost(token="hunter2", bind="127.0.0.1",
                         port=0, fps=10, quality=70)
host.start()
print("listening on", host.port, "viewers:", host.connected_clients)
```

```python
# 控制另一台机器——连上去并发送输入
from je_auto_control import RemoteDesktopViewer
viewer = RemoteDesktopViewer(host="10.0.0.5", port=51234, token="hunter2",
                             on_frame=lambda jpeg: ...)
viewer.connect()
viewer.send_input({"action": "mouse_move", "x": 100, "y": 200})
viewer.disconnect()
```

也可以用 IP 允许列表（CIDR 网段或具体地址）限制谁能连进来，列表外的对端在握手
阶段就会被拒绝：

```python
RemoteDesktopHost(token="tok", ip_allowlist=["10.0.0.0/8", "192.168.1.100"])
```

---

## 平台支持

| 平台 | 后端 | 输入 | 屏幕捕获 | 录制 | 窗口管理 |
|---|---|:---:|:---:|:---:|:---:|
| Windows 10 / 11 | Win32 ctypes（可选 Interception 驱动） | ✅ | ✅ | ✅ | ✅ |
| macOS 10.15+ | pyobjc / Quartz | ✅ | ✅ | ✅¹ | ✅ |
| Linux X11 | python-Xlib（可选 `uinput`） | ✅ | ✅ | ✅ | ✅ |
| Linux Wayland | 经桌面 portal 的 libei，或 ydotool／wtype ＋ 截图工具 | ✅ | ✅ | ❌ | ❌ |
| FreeBSD／OpenBSD／NetBSD | python-Xlib，与 Linux 同一套 X11 后端 | ✅² | ⚠️² | ✅² | ✅² |
| Android | adb + uiautomator2 | ✅ | ✅ | — | — |
| iOS | WebDriverAgent / facebook-wda | ✅ | ✅ | — | — |

¹ macOS 的录制走 Quartz event tap，需要**辅助功能**权限
（系统设置 → 隐私与安全性 → 辅助功能）。没有授权时会直接抛出并指名
缺的是哪个权限，而不是安静地录到一个空的 session。

² BSD 直接跑同一套 X11 后端——同一个 X server、同一个 `python-Xlib`，而输入、
录制与窗口管理就只依赖这一个包。`freebsd` CI job 在真的 FreeBSD 14 上驱动真的
输入，再从 X server 读回来；OpenBSD 与 NetBSD 走同一条代码路径，只是没有 CI
runner。唯一的例外是屏幕截取，卡住的是打包而不是平台：它走 Pillow／mss 与
OpenCV，而 `opencv-python`、`pillow`、`cryptography` 都没有发 FreeBSD wheel。
从 ports 构建之后，截取、图像匹配、OCR 与动作加密也都能用——
`import je_auto_control` 本身已经不需要它们任何一个。

Wayland 的按键、按钮与指针输入在 `auto` 模式下，仅在可选原生后端缺失时改用 CLI。
portal 请求开始后，拒绝、超时、握手失败、设备暂停或权限撤销都会停止输入，
不会自动切换提供者；重复调用保留不含原生资源的失败状态，不重开同意对话框。
`JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei` 强制原生输入，`=cli` 明确选择 CLI。
解决权限问题后，可明确调用 `je_auto_control.linux_wayland.libei.reset_default_backend()`
以允许重新请求。原生组合键中断时会在同一后端尝试释放所有已按下的按键，并保留原始取消。
此行为不改变明确的 wtype 文本输入路径或屏幕截取选择。

`ydotool` 退路需要
**ydotool 1.0 以上**。AutoControl 送的每一个参数都是那一版才有的；0.1.x
（Debian bookworm 与目前所有 Ubuntu 仍以这个名字提供，Debian trixie 则根本没有）
对同一批参数返回 0 却不送出任何事件。AutoControl 会检测并直接拒绝，
而不是为根本没送出的输入回报成功。Arch、Fedora 与 Debian unstable 提供的是 1.0。

这条退路要能**准确定位**，还有一个前提:合成器的指针加速度必须是关的。
`ydotool mousemove --absolute` 并不发任何绝对事件——它先把光标推到合成器夹取的
那个角落，再发相对位移，所以这段位移会被合成器加速。对真的 wlroots session 量到的是:
libinput 的默认 profile 让光标走的距离正好是请求的两倍。ydotool 自己的 `--help`
也是这样写的；AutoControl 每个进程会记一次警告，而不是安静地把点击放到错的地方。
请对 ydotoold 的设备关掉加速度（sway:`input type:pointer accel_profile flat`
加上 `pointer_accel 0`），或者装上 `liboeffis`，改走协议层本来就是绝对坐标的 libei。

倍率是合成器自己的设置，客户端读不回来，所以只有你知道它关了没有：
`JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat` 表示已经关掉，移动就不再出声；
`=strict` 则宁可拒绝这次移动，也不让点击落在别的地方；不设置就维持
“警告一次后照样移动”的默认。

Wayland 的屏幕截取需要合成器对应的工具，因为没有单一工具能覆盖全部：wlroots 系
（sway、Hyprland、river）用 `grim`，GNOME 用 `gnome-screenshot`，KDE 用 `spectacle`。
装好其中一个之后，所有截取路径——截图、图像与锚点定位、OCR、屏幕录制、远程桌面——都会
经由它。三个都没装时，内置 D-Bus client 会通过 session bus 尝试 `xdg-desktop-portal`，第一次可能会弹
同意对话框。再不行，截取会带着安装提示明确失败，而不是返回空白的 XWayland root；
`je_auto_control.api.run_diagnostics()`（以及 GUI 的 Diagnostics 标签页）的 `screen_capture`
检查会报告当前使用的是哪一层。

原生 Wayland 指针坐标在原始坐标与布局原点换算后仍不属于任何授权 EIS 区域时，
会以 `state="failed"` 的 `LibeiUnavailable` 拒绝，停止自动 CLI 备用，
不发送移动、frame 或后续点击。有效坐标、未提供区域的设备、同一 sender 的后续有效请求，
以及显式选择 CLI 的现有行为保持不变。

**输入／截取能力**提供 `je_auto_control.api`（也由包根目录导出）的
`BackendContext`、`CapabilityStatus`、`CapabilitySnapshot` 与 `probe_capabilities`。
调用 `probe_capabilities(BackendContext.current()).to_dict()`、无参数的
`AC_probe_capabilities`／只读 `ac_probe_capabilities`，或选择
**Diagnostics → Actions → 查看输入与截取能力**；Builder 提供相同无参数命令。
`python -m examples.capabilities` 显示本机前置条件与确定性的 XWayland 范围示例，不操作桌面。

输入项描述按键／指针事件；现有 wtype 文字路径独立。探测只读环境、PATH 与不等待锁的现有原生状态，
不加载可选原生库、不连接、不读取事件、不截取或请求授权。找到工具或 bus 地址只代表
`unverified`，不等于可用。缓存 libei 须完成握手，且键盘、绝对指针、按钮与滚轮事件种类都在运行才报告可用；
部分授权保持未验证，事件种类暂停或必要设备移除则报告暂停／撤销。八种状态为 `available`、`unverified`、`needs_permission`、
`needs_dependency`、`unsupported`、`paused`、`revoked`、`failed`。
`available` 仅是最近的本机观察，可能过时；实际操作仍重新验证权限。XWayland 一律
`desktop_wide=False`，无法覆盖原生 Wayland 窗口；其他范围标记仍受授权区域限制，不代表已验证每个屏幕。

Context 会复制环境／工具数据，可由拥有者提供无原生对象的输入／截取观察，但不授予权限。
默认本机结果不含环境值、命令参数、可执行文件路径或原生错误文字；AC／MCP 不接受外部提供观察。
显式选择 CLI 与观察到可选原生依赖缺失后的自动备用分开；拒绝、暂停、撤销与失败不表示改走 CLI。
截取工具／portal 选择独立诊断，重绘与切换语言只使用现有快照。原生 portal 恢复、compositor 重启、
截取结果与 context 的接合，以及原生 session 的重试／取消／停止控制仍列于 `Progress.md`。

GUI 工作基础提供 `gui.task_controller.TaskController`：
`submit(work, owner=widget)` 返回调用者持有的 `TaskHandle`，通过
`TaskOutcome`／`TaskProgress` 传递终态与进度。工作取得不依赖 Qt 的
`CancellationToken`，提供 checkpoint、有界且可被取消唤醒的等待与进度报告。
提交时捕获 context，执行前重新读取 store 用户；工作须持有数据、不引用 widget，并验证自身操作所需的 capability。
现有 `DeferredAuthorization.scope()` 保持输入权限要求，`context_scope()` 仅更新并绑定身份。

拥有者、handle 或 controller 销毁时会请求协作式停止并丢弃延迟结果；每项工作有独立 ID／token，
回调在 GUI 线程执行。不强制中断不配合的调用，也不把已成功提交的结果改标为取消。
错误与进度使用捕获的秘密遮罩 scope，终态不保留异常 traceback；线程启动失败会恢复两层登记并保留原失败。
Diagnostics 已接入此共用控制器；其余面板／backend 迁移与原生 session 操作仍列于 `Progress.md`。

主动 **Diagnostics → Actions → 运行诊断** 以共用控制器在 GUI 线程外运行。
**停止诊断** 请求协作式停止；四种语言的状态区分运行中、清理中、已取消和失败，并显示已完成检查数。
重复运行不另开工作，关闭后丢弃延迟进度／结果，显式重试会建立新的拥有者工作。
GUI 以不保留异常 traceback 的 typed outcome 呈现取消；核心／SDK／CLI 与 MCP handler
保持原始直接／包装取消对象。普通检查错误仍计入报告并继续其余项目。

两个 SDK namespace 导出 `CancellationToken`、`TaskProgress`、`cancellation_scope`。
使用 `with cancellation_scope(token): report = run_diagnostics()`，拥有者可由另一线程调用
`token.cancel()`；现有无参数诊断签名不变。Scope 不授予权限，`cancellation_scope(None)`
只在有时限的自有资源清理期间暂停取消。`AC_diagnose` 与新增的只读 `ac_diagnose` 共用报告；
MCP 不接受参数，使用请求取消／进度，与显式 GUI 操作同样需要 `read_screen`，拒绝外部 token／授权数据。
这些是主动检查，截取可能请求同意；`ac_probe_capabilities` 保持独立的被动选项。

Scoped Wayland D-Bus 的连接／读取／部分写入，以最多 0.1 秒的间隔轮询，保持原本总时限。
取消时在原 bus 以独立 0.25 秒预算尝试 Request.Close，再释放连接；取消的已返回图片会删除。
Scoped CLI 截取会停止并回收自己建立的 helper／process group，清理有时限，pipe close 失败也不覆盖原取消，
已回收的数字 PID 不再作为信号目标。liboeffis 获取 session 时会观察停止并释放自身 context。
不强制中断不配合或原生调用，清理期间 GUI 仍可操作；restore／重启、原生 session 控制、
截取拥有者 metadata 与其余面板／backend 迁移保留于 `Progress.md`。

`python -m examples.cancellable_diagnostics` 默认只做受控取消示例，不调用 provider。
`--active --cancel-after 2` 才显式运行诊断并在两秒后请求停止；真机／设备／API 验收另外列管。

打开 Diagnostics 只显示已翻译的「尚未运行」状态，不执行检查。
选择 **Actions → 运行诊断** 才会启动现有主动检查，可能截取屏幕或需要 portal 同意；
切换语言不启动检查。显式的 `run_diagnostics`、`AC_diagnose` 与 MCP 诊断调用保持主动行为；
无副作用的能力查看使用下方独立操作。

未完成的 screenshot portal 请求会在断开原始 bus 前尝试 `Request.Close`，
使用独立的 0.25 秒 D-Bus I/O 预算。服务器返回替代 handle 时会跟随该 handle；
方法回复不确定时则使用预测 handle，已完成的 Response 不重复关闭。
普通清理错误不覆盖主要截取失败；原始取消与强制中断对象会穿过包装及清理继续传播。
D-Bus 写入与回复共用调用预算，连接建立有明确时限，connect／认证／Hello 中断时，
即使 `__enter__` 失败也会释放自己拥有的描述符。实际合成器／对话框取消仍待平台验收。

有一件只在 Wayland 出现、需要事先规划的事：**截取回来的图里可能有鼠标光标。**
这里没有任何一条截取请求光标，但只要 backend 没有光标平面（包含任何以
`WLR_NO_HARDWARE_CURSORS=1` 运行的 session），wlroots 就会画**软件光标**并把它
合成进输出缓冲区，而截取交回来的正是那一份。Windows 与 X11 都不含光标，所以
“定位器、模板匹配或 OCR 在目标中间看到一个光标形状的洞”只会在这里发生。
Wayland 不让客户端读光标位置，所以没有东西可以可靠地遮或避开：请在截取之前
把指针移离要拍的区域。`screen_capture` 检查会以 `cursor_may_be_captured` 报告这件事。

如果以上都不适用你的环境，可以直接指定自己的命令——它优先于所有检测，`{output}` 会被
换成临时 PNG 路径：

```bash
export JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mycapture --png {output}"
```

Wayland 禁止非特权客户端进行全局输入录制——若要录制，请设置
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` 并在 X11 会话下运行。窗口管理支持
Windows、macOS（pyobjc）与 X11（含 XWayland）；纯 Wayland 会话的协议不让客户端看到其他程序的窗口，
所以 `list_windows()` 返回空列表，其余窗口操作一律抛出带原因的 `AutoControlUnsupportedOperationException`。对于会忽略合成输入的应用，
可选用驱动层后端（`JE_AUTOCONTROL_WIN32_BACKEND=interception`、
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`、ViGEm 虚拟手柄）；驱动未安装时会自动回退到原有行为。

---

## 文档与示例

| 资源 | 内容 |
|---|---|
| [`examples/`](../examples/) | 43 个自包含脚本：截图点击、OCR、调度器、远程桌面、agent loop、可观测性、录制、变量、热键、触发器、报表、MCP、REST、密钥、插件、computer use、Wayland、跨主机 DAG、chat-ops、pytest/BDD、锚点定位、动作日志。 |
| [Read the Docs](https://autocontrol.readthedocs.io/en/latest/) | 完整 API 参考，含英文与中文。 |
| [architecture_explore.md](../architecture_explore.md) | 逐层记录每个模块的职责。 |
| [docs/CAPABILITY_MATRIX.md](../docs/CAPABILITY_MATRIX.md) | 能力 × 平台对照矩阵。 |
| [docs/API_LIFECYCLE.md](../docs/API_LIFECYCLE.md) | 稳定 API 与弃用策略。 |
| [docs/updates/](../docs/updates/README.md) | 更新记录：各版本说明与完成的工作，每月一个文件（原 `WHATS_NEW.md`）。 |
| [CHANGELOG.md](../CHANGELOG.md) | 兼容性变更记录。 |
| [SECURITY.md](../SECURITY.md) | 安全策略与报告方式。 |

---

## 开发

```bash
git clone https://github.com/Integration-Automation/AutoControlGUI.git
cd AutoControl
pip install -r dev_requirements.txt
uv sync                 # 或：以已提交的 uv.lock 做可重现安装
```

```bash
python -m pytest test/unit_test/headless      # 无头单元测试
python -m pytest test/integrated_test/        # 跨模块流程测试

ruff check je_auto_control/
pylint je_auto_control/
bandit -c pyproject.toml -r je_auto_control/
```

dev／main 的无头任务会保留七天的 `native-<os>-<python>` artifact，内含合并进程输出、
包／运行环境版本与退出码。Linux 经 GDB 保留各线程原生堆栈；其他平台保留 Python
faulthandler 输出，测试失败仍会使任务失败。可在 repo 执行单一命令
`python scripts/ci_native_diagnostics.py --artifact-dir test-artifacts -- python -m pytest -v --tb=short --timeout=120`；
Linux 安装 GDB 后，可在 `--` 前加入 `--native`。
含空格／引号的 argv 仍是原始参数，已处理的 `SIGINT` 会传给子进程。
Linux 先在完整套件的 debugger 外验证诊断工具；前置检查记录也收在同一 artifact。

选定的 dev 推送由 `.github/workflows/ei-lifecycle.yml` 在隔离 libei／libeis
容器执行，将版本及两份原生记录保留于 `ei-lifecycle-<run>-<attempt>` artifact 十四天。
半开与 live 释放子进程分别有十／六十秒时限与 faulthandler；其他子进程失败使 CI 失败，
释放成功必须有 begin／end 标记。半开探测另须有相同整数 fd 数量，live 清理先释放拥有的
device refs。run 39507190704 在 libei／libeis 1.3.901-1 通过 9/9 与 20/20 检查，
包含坐标越界拒绝且不转用 CLI。半开 `ei_unref` 仍会 SIGSEGV，因此保留 runtime 保护，
helper 隔离仍待完成。设备暂停与序号回读仍未验证；受控 socket peer 不代表合成器授权、
真机或多屏幕验收。

欢迎贡献——请见 [CONTRIBUTING.md](../CONTRIBUTING.md) 与
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)。CI 会强制两条规则：`import je_auto_control`
绝不能加载 PySide6；每个功能都必须同时具备无头 API 与 GUI 界面。

---

## 许可

[MIT License](../LICENSE) © JE-Chen。
内含与可选第三方组件的许可请见 [Third_Party_License.md](../Third_Party_License.md)。

- **主页**：https://github.com/Integration-Automation/AutoControlGUI
- **PyPI**：https://pypi.org/project/je_auto_control/
- **文档**：https://autocontrol.readthedocs.io/en/latest/

旧式 MCP 动作包装、并行分支及本机 DAG worker 也会保留相同的来源限制。

受管指针动作可指定该次观察的元素索引或缩略图坐标，由主机检查当前画面并换算原生坐标，包括缩放与负屏幕原点。收据保存几何依据，不保存图像字节。`AgentObservationStale` 表示分派前已拒绝动作；本机 agent 只在 adapter 确认没有按住或待处理输入时，在重试预算内重新观察。

紧急停止先返回带有 metadata.details_deferred 的精简状态，完整产物链接可由单个任务查询。

托管鼠标按下前会规范按钮所有权并确认实际光标位置。Windows 指针检查会拒绝其他窗口遮挡。影像仅将指定窗口绘制到清空的私有 GDI 内存，几何变化会拒绝该画面；绘制或读取失败也会释放资源。不改用桌面捕获。这些路径已用模拟原生 API 测试，实际原生验收仍未验证。

Agent 任务界面将任务范围、工作流程设置、触发器、技能及恢复分页。观察页显示只读元素和已验证、严格遮罩的 JPEG，每个逻辑画面像素对应一个呈现像素。选择元素或影像坐标只会编辑该次观察的动作请求；由 Actions 的「执行观察动作」通过共用任务 API 发送。切换任务会清除预览，迟到回复不能替换当前任务；新画面必须重新选择，旧索引不能直接复用。关闭界面仅解除请求订阅。

托管工作流程可用 workflow_wait／AC_workflow_wait 等待指定控件的精确值或状态，只重复读取；可取消且受动作预算限制，默认五秒、上限六十秒，不重发写入或提交。固定技能每一步都验证已有收据与固定顺序，恢复也不能跳过读回失败的步骤；模型自主循环仍保留停滞检测。新表单／跨应用模板会在提交前拒绝原本已匹配的确认值，提交后等待新的状态转换。批次可设置 new_record_selector 逐条重置；确认仅证明配置的界面转换，有交易标识值时应使用它。归档模板完成时会重读指定清单及文件摘要，清单上限一 MB，总验证数据上限六十四 MiB。

AgentHumanReview 表示未保存内容或未知对话框需人工审核；包括外部观察请求都会记录 waiting_user 并释放输入控制权，明确恢复后仍会重新检查。Windows 依据原生对话框／禁用所有者及英中日已知未保存文字判断。Workspace 也会拒绝标题首尾带星号的文档，并可在窗口设置中加入 unsaved_selector 与 unsaved_value，在改变排列前检查应用特有指示；不声称能推断所有程序的未保存状态。标准文件对话框沿用 AC_handle_file_dialog 执行器，托管 driver 只接受唯一精确标题、相同 PID、已确认前景，以及授权根目录内的绝对路径。UIA 控件须属于实际指定的根窗口，同 PID 的其他窗口也会拒绝。模拟原生与本机 HTTP 测试已有覆盖，实际平台验收仍未验证。

主机目标通过 AgentTargetProfile 与 manage_agent_target（AC_agent_target，register/get/disable/enable/probe）设置。名称及设置固定不可替换，目前提供 desktop／files／browser adapter，未实现类型会被拒绝；浏览器可使用主机审阅的 helper_python。任务固定主机设置摘要，不能扩大工具、应用、根目录或网络来源。启停状态会跨重启保存并在分派时检查；禁用会请求暂停及清理，重新启用仍须明确恢复任务。list_agent_targets／AC_agent_target_list／CLI agent-task targets 仅提供被动信息，readiness=not_probed、native_evidence=not_recorded；完整设置需要 manage_hosts。CLI agent-task target 及 GUI「主机目标」页使用同一服务。匿名有效 MCP 工具 session 的直接及旧式包装调用都以 operator 权限执行；MCP 主机管理需要已验证的管理员，可信任的直接 Python 调用维持原行为。浏览器自动化统一由 WebRunner（je_web_runner）提供，本机开发来源为 D:/Codes/WebRunner；browser profile 使用受管 je_web_runner SDK 契约，依赖诊断不代表原生可用。

既有浏览器自动化（包括 open_path(URL) 与 AC_open_path）统一交由 WebRunner，Python 包名为 je_web_runner。URL 计划的 backend 现为 je_web_runner，原本比较 webbrowser 描述值的调用端需改用新值；函数接口与本机文件打开维持兼容。实际 URL 执行需要配置的 WebRunner 项目，缺少时传出 WebRunnerBridgeError，不改用 OS 浏览器。本机开发来源为 D:/Codes/WebRunner；纯计划及注入 opener 测试不需要该包。协议支持由 WebRunner 与所选浏览器决定。既有浏览器 GUI／MCP／AC 及录制的 WR_* 动作都使用同一桥接。
