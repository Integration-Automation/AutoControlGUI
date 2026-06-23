# 本次更新 — AutoControl

## 本次更新 (2026-06-23) — 动作前接地防护

拒绝越界点击;把接近偏离者吸附到真正的元素。完整参考:[`docs/source/Zh/doc/new_features/v153_features_doc.rst`](../docs/source/Zh/doc/new_features/v153_features_doc.rst)。

- **`validate_action` / `snap_to_element` / `in_bounds`**(`AC_validate_action`):`guardrail` 扫文字、`loop_guard` 检测循环——两者都不在派发前验证坐标动作,所以幻觉 `(9999,-5)` 点击会打到空处、偏 5px 的点击会错过。本功能拒绝屏幕外坐标,并在提供 `targets` 时把接近偏离者吸附到最近元素中心,返回 `{ok, reason, snapped}`。纯标准库几何,作用于元素字典;执行器 `screen` 默认为实际屏幕。可无头测试;接在 agent 循环派发之前。

## 本次更新 (2026-06-23) — 符记预算内的无障碍文字观测

把无障碍树转成 VLM 可操作的已编号文字区块。完整参考:[`docs/source/Zh/doc/new_features/v152_features_doc.rst`](../docs/source/Zh/doc/new_features/v152_features_doc.rst)。

- **`serialize_observation` / `observation_index` / `flatten_tree`**(`AC_serialize_observation`、`AC_observation_index`):`describe_screen` 给角色*数量* + 平面标签列表——没有稳定索引、没有 `[12] button "Submit" @(x,y)` 行、没有视口裁切、没有符记预算。本功能把(嵌套)元素树扁平化为仅互动项、裁切到视口、依阅读顺序排序、上限 `max_elements`、指派稳定 `index`,并渲染模型可操作的行(「click [12]」)。纯标准库,作用于元素字典;与 `fuse_elements`/`set_of_marks` 搭配。可无头测试。

## 本次更新 (2026-06-23) — 标准化 Computer-Use 动作结构

把 Anthropic / OpenAI agent 动作桥接到 AutoControl 命令。完整参考:[`docs/source/Zh/doc/new_features/v151_features_doc.rst`](../docs/source/Zh/doc/new_features/v151_features_doc.rst)。

- **`from_anthropic` / `from_openai_cua` / `to_ac_command` / `canonical_action`**(`AC_cua_command`):`tool_use_schema` 导出 AC_* 签章、`coordinate_space` 缩放——两者都不*正规化进来的动作载荷*。Anthropic 发出 `{action:"left_click", coordinate:[x,y]}`、OpenAI CUA 发出 `{type:"click", x, y, button}`;这些转接器把两者对应为标准动作再对应为可执行的 `[AC_*, params]`(含可选坐标空间 `scale`)。纯标准库、可无头测试;执行器命令对任一来源返回 `{canonical, command}`。

## 本次更新 (2026-06-23) — 窗口客户区几何

不论标题栏 / 边框,点击窗口*内部*。完整参考:[`docs/source/Zh/doc/new_features/v150_features_doc.rst`](../docs/source/Zh/doc/new_features/v150_features_doc.rst)。

- **`get_client_rect` / `client_point` / `frame_insets` / `client_to_screen`**(`AC_get_client_rect`、`AC_client_point`):`get_window_geometry` 只返回*外框*——没有客户区矩形、框边内缩运算或客户区→屏幕对应。`client_point("App", x, y)` 把内容相对点对应到屏幕,让点击不论外框都落在窗口内;`frame_insets` 报告边框 / 标题栏厚度。`frame_insets`/`client_to_screen` 是纯几何(可无头测试);`get_client_rect` 使用可注入的 Win32 读取器(`GetClientRect`+`ClientToScreen`)。

## 本次更新 (2026-06-23) — 感知式(YIQ)图像比对含反锯齿抑制

会忽略反锯齿边缘的视觉回归比对。完整参考:[`docs/source/Zh/doc/new_features/v149_features_doc.rst`](../docs/source/Zh/doc/new_features/v149_features_doc.rst)。

- **`perceptual_diff` / `assert_perceptual`**(`AC_perceptual_diff`):`image_difference` 计算原始逐通道差、`ssim_compare` 是整体分数——两者都未使用感知式度量也不忽略反锯齿(视觉比对误报的首要来源)。本功能在 YIQ 空间比较(pixelmatch 的色彩度量),并预设以形态学开运算移除单像素反锯齿细边差异,只计算实心变化(`include_aa=True` 保留)。返回 `{diff_pixels, diff_ratio, regions}`;`assert_perceptual` / `max_diff_ratio` 把关回归测试。可注入图像配对 → 无头可测(1px 细边 → 0、实心区块 → 计入)。

## 本次更新 (2026-06-23) — 软性断言(汇整所有失败)

验证很多项,一次报告每一个失败。完整参考:[`docs/source/Zh/doc/new_features/v148_features_doc.rst`](../docs/source/Zh/doc/new_features/v148_features_doc.rst)。

- **`SoftAssertions`**(`AC_soft_assert`):`assert_all` 接受事先建好的规格列表——没有可随处调用 `check()`、并在区块退出时一次抛出全部的作用域累加器(JUnit5 `assertAll` / Playwright `expect.soft`)。`with SoftAssertions() as soft: soft.check(...)` 记录通过/失败(区块中永不抛出、返回布尔值可分支),退出时一次抛出列出每个失败——且永不遮蔽已在传播的异常。执行器命令汇整 JSON `checks` 列表(eq/ne/gt/lt/contains/truthy)。纯标准库、可无头测试。

## 本次更新 (2026-06-23) — 窗口 Z-order(置顶 / 最前 / 最后)

把窗口钉在最上层、移到最前、或推到后面。完整参考:[`docs/source/Zh/doc/new_features/v147_features_doc.rst`](../docs/source/Zh/doc/new_features/v147_features_doc.rst)。

- **`set_topmost` / `bring_to_front` / `send_to_back` / `plan_zorder`**(`AC_set_topmost`、`AC_bring_to_front`、`AC_send_to_back`):原始 `set_window_position` 存在但未在 facade、无标题包装也无 topmost 语意——缺少标准 RPA 的「置顶」。`plan_zorder` 是纯动作→`SetWindowPos` 常数查找(可无头测试);以标题操作的设定器透过可注入 driver(`snap_window` 接缝模式)套用,默认为 Win32。

## 本次更新 (2026-06-23) — 局部动态 / 活动检测

找出两帧之间哪些子区域在动。完整参考:[`docs/source/Zh/doc/new_features/v146_features_doc.rst`](../docs/source/Zh/doc/new_features/v146_features_doc.rst)。

- **`changed_regions` / `has_motion` / `activity_score`**(`AC_changed_regions`、`AC_has_motion`):`wait_until_screen_stable` 是布尔轮询、`ssim_changed_regions` 是结构性(忽略快速动态)、`diff_screenshots` 非活动区块。本功能是便宜的 absdiff 路径——对逐像素差做门槛、膨胀,返回移动区域方框(由大到小)、布尔值,以及移动像素比例。挑选安静区域或定位转圈动画。两个可注入帧 → 无头可测;沿用共用连通元件辅助;执行器中 `after` 默认为即时屏幕截取。

## 本次更新 (2026-06-23) — 色彩直方图指纹与变化检测

判断画面在光照 / 缩放下是否仍是「同一个」。完整参考:[`docs/source/Zh/doc/new_features/v145_features_doc.rst`](../docs/source/Zh/doc/new_features/v145_features_doc.rst)。

- **`image_histogram` / `compare_histograms` / `histogram_changed`**(`AC_image_histogram`、`AC_histogram_changed`):`image_dedup` 的感知哈希是空间性的(对颜色/主题脆弱)、`color_stats` 只有单一颜色。归一化色彩直方图是耐光照/缩放的「同一画面、还是调色板变了?」信号(主题切换、重载、旋转横幅)。`image_histogram` 返回逐通道直方图(`hsv`/`rgb`/`gray`);`compare_histograms` 提供 correlation/chisqr/intersection/bhattacharyya;`histogram_changed` 比较参考与实际屏幕。可注入图像 → 无头可测;OpenCV 核心(`cv2.calcHist`/`compareHist`)。

## 本次更新 (2026-06-23) — 丰富剪贴板(HTML / CF_HTML)

把*格式化*的 HTML 复制粘贴到 Word / Outlook。完整参考:[`docs/source/Zh/doc/new_features/v144_features_doc.rst`](../docs/source/Zh/doc/new_features/v144_features_doc.rst)。

- **`build_cf_html` / `parse_cf_html` / `set_clipboard_html` / `get_clipboard_html`**(`AC_set_clipboard_html`、`AC_get_clipboard_html`):基础剪贴板只处理纯文字 + 图像——富文字粘贴需要 `CF_HTML`,其字节偏移标头(`StartHTML`/`EndHTML`/`StartFragment`/`EndFragment`)极易出错。`build_cf_html`/`parse_cf_html` 以纯 Python 计算与还原它(往返测试、多字节 UTF-8 正确);`set/get_clipboard_html` 将其包装于 Win32 剪贴板(含纯文字后备)。字节偏移运算可无头测试;只有 I/O 为 Windows。

## 本次更新 (2026-06-23) — 可串接 / 可过滤的候选定位器

用链式调用细化已定位的元素:`.within(panel).filter(has_text="Delete").nth(1)`。完整参考:[`docs/source/Zh/doc/new_features/v143_features_doc.rst`](../docs/source/Zh/doc/new_features/v143_features_doc.rst)。

- **`from_boxes` / `Candidates`**(`AC_locate_chain`):`anchor_locator` 是单一关系、`grid_locator` 是单元格——两者都不支援对候选集合做可组合细化(Selenium-4 / Playwright 的链式定位惯用法)。本功能是对来自*任何*来源(模板 / OCR / a11y / `fuse_elements`)的框做纯后置过滤:`within`(区域裁切)、`filter`(`has_text` / `near` / 面积 / predicate)、`sort_reading`、`nth` / `first` / `last`、`resolve()` / `center()`。每个方法返回新的 `Candidates`(不变动)→ 完全无头可测。执行器命令套用 JSON `ops` 列表。

## 本次更新 (2026-06-23) — 重试式数值断言(expect.poll)

重试*任意*值直到符合,不只限内建检查。完整参考:[`docs/source/Zh/doc/new_features/v142_features_doc.rst`](../docs/source/Zh/doc/new_features/v142_features_doc.rst)。

- **`expect_poll` / `assert_poll` + matchers**(`AC_expect_poll`):`assert_eventually` 只能轮询固定字典规格检查(文字/图像/像素/…)。本功能对任意零参数 `getter` 以任意 `matcher`(`to_equal` / `to_contain` / `to_be_greater_than` / `to_match_regex` / `to_be_truthy` / `to_be_stable`)轮询直到通过或超时——OCR 出的总额、行数稳定、自定义判断式皆可。可注入 `clock`/`sleep` → 具确定性,对应 Playwright 的 `expect.poll`。执行器命令会重复执行嵌套动作直到其结果某键符合。

## 本次更新 (2026-06-23) — 线条 / 网格 / 分隔线检测(Hough)

从原始像素找出表格网格线与 UI 分隔线。完整参考:[`docs/source/Zh/doc/new_features/v141_features_doc.rst`](../docs/source/Zh/doc/new_features/v141_features_doc.rst)。

- **`find_lines` / `find_grid` / `find_separators`**(`AC_find_lines`、`AC_find_grid`、`AC_find_separators`):`grid_locator` 分群*已找到*的框、`shape_locator` 找封闭矩形——两者都无法从像素找出表格网格线或分隔线。Canny + 概率 Hough 检测直线段(分类水平/垂直/斜向),`find_grid` 还原 `{rows, cols, cells}` 让你定址「第 3 行、第 2 列」,`find_separators` 返回长分隔线坐标。可注入 haystack → 无头可测;OpenCV 核心(`cv2.HoughLinesP`)。

## 本次更新 (2026-06-23) — 免模型文字区检测(MSER)

不跑 OCR 也能找出画面上文字的位置。完整参考:[`docs/source/Zh/doc/new_features/v140_features_doc.rst`](../docs/source/Zh/doc/new_features/v140_features_doc.rst)。

- **`find_text_regions` / `find_text_lines`**(`AC_find_text_regions`、`AC_find_text_lines`):`shape_locator` 找矩形(不是文字)、`locate_text` 需要 OCR 引擎*以及*确切字串——两者都无法回答「哪里有*任何*文字?」。MSER 找出字元 / 词 / 行区块,让脚本能裁切候选框喂给 OCR(比全画面更快更准),或在未安装 OCR 相依时检测标签出现。`merge` 并集 MSER 逐字元的嵌套区域;`find_text_lines` 将字元归为逐行框;空白画面返回 `[]`。OpenCV 核心(`cv2.MSER_create`)、可注入 haystack → 无头可测。

## 本次更新 (2026-06-23) — HSV 色彩空间分割

不论光照都能找出「任一色阶的红色」。完整参考:[`docs/source/Zh/doc/new_features/v139_features_doc.rst`](../docs/source/Zh/doc/new_features/v139_features_doc.rst)。

- **`dominant_hue_regions` / `segment_hsv` / `color_mask`**(`AC_dominant_hue_regions`、`AC_segment_hsv`):`find_color_region` 在 RGB 以各通道 ± 框遮罩——无法匹配「同一颜色但不同亮度」(状态灯、强调色、主题色调)。HSV 把色相与亮度分离,因此「色相带 + 饱和度 / 明度下限」可在不同光照下捕捉所有色阶。`dominant_hue_regions(hue=…)` 自动处理红色 0/180 环绕;`segment_hsv` 接受明确带;两者皆返回 `{x,y,width,height,area,center}` 区块并沿用共用连通元件辅助函数。可注入 haystack → 无头可测。

## 本次更新 (2026-06-23) — 融合并排序屏幕元素框

把原始的 OCR + 图标 + a11y 框转成一份干净、已编号的元素列表。完整参考:[`docs/source/Zh/doc/new_features/v138_features_doc.rst`](../docs/source/Zh/doc/new_features/v138_features_doc.rst)。

- **`iou` / `merge_boxes` / `fuse_elements` / `reading_order`**(`AC_fuse_elements`、`AC_reading_order`):`set_of_marks` 为干净的元素列表编号,但没有任何功能*产生*它——真实画面解析会产出三个彼此重叠、有重复且无顺序的来源。本功能补上这一步:依 IoU 去除近重复框、并集 OCR/icon/a11y 并在重叠时保留最可信来源(`source_priority` a11y > ocr > icon)、再由上到下 / 由左到右排序并给予稳定 `index`。纯 `dict` 框 → 纯标准库、完全无头可测;直接与 `set_of_marks` 搭配。

## 本次更新 (2026-06-23) — 可操作性闸门(操作前先等待就绪)

目标真正就绪前不要点击。完整参考:[`docs/source/Zh/doc/new_features/v137_features_doc.rst`](../docs/source/Zh/doc/new_features/v137_features_doc.rst)。

- **`wait_actionable` / `act_when_ready`**(`AC_wait_actionable`):Playwright/Cypress 在每次点击前都会做可操作性检查——存在 + 已停止移动 + 启用 + 未被遮盖——但 AutoControl 先前没有(`self_heal_click` 立即点击;`wait_until_screen_stable` 观察整个画面)。本功能把这四项合成单一闸门,返回 `ActionabilityReport`(各项检查布尔值、目标 `point`、`reason` = 第一个失败的检查)。每个信号都是可注入 callable(`bbox_provider` / `region_sampler` / `enabled_probe` / `hit_tester`)再加可注入 `clock`/`sleep`,因此完全确定性且可无头测试。执行器命令以模板图像把关。

## 本次更新 (2026-06-23) — 多显示器 / 虚拟桌面几何

在多台显示器间正确摆放窗口与坐标。完整参考:[`docs/source/Zh/doc/new_features/v136_features_doc.rst`](../docs/source/Zh/doc/new_features/v136_features_doc.rst)。

- **`enumerate_monitors` + `Monitor` / `virtual_bounds` / `monitor_at_point` / `monitor_for_window` / `to_local` / `to_virtual` / `remap_point`**(`AC_enumerate_monitors`、`AC_monitor_at_point`):`snap_window` / `arrange_grid` / 版面规划器都假设单一主屏 `(width, height)`——对多显示器无感,无法在第二台显示器铺排或处理负原点虚拟桌面。本功能补上实体层:并集虚拟边界、某点 / 某窗口属于哪台显示器、虚拟↔显示器区域坐标转换,以及跨分辨率 / DPI 的等效位置重映射。对 `Monitor` dataclass 的纯几何 → 完全无头可测;`enumerate_monitors` 具可注入 provider(默认 `mss`)。

## 本次更新 (2026-06-23) — 图像预处理(供 OCR / 模板匹配)

在识别或匹配前先清理画面。完整参考:[`docs/source/Zh/doc/new_features/v135_features_doc.rst`](../docs/source/Zh/doc/new_features/v135_features_doc.rst)。

- **`preprocess_image` + `to_grayscale` / `binarize` / `upscale` / `denoise` / `deskew` / `enhance_contrast`**(`AC_preprocess_image`):`locate_text` 与 `match_template` 把*原始*截取直接喂给 OCR / 匹配器——小字、暗色主题、低对比与歪斜会严重影响两者,而框架毫无预处理接缝。本功能加入标准流程(灰阶 → 放大 → 二值化 → 去歪斜 → 去噪 → CLAHE),倍增其准确度。可注入 haystack → ndarray;`detect_skew_angle` 测量文字旋转;`binarize` 提供 otsu / adaptive。执行器命令把清理后图像写入路径。可对合成数组无头测试。

## 本次更新 (2026-06-23) — 排列多个窗口(网格 / 层叠)

一次调用排好一整组窗口。完整参考:[`docs/source/Zh/doc/new_features/v134_features_doc.rst`](../docs/source/Zh/doc/new_features/v134_features_doc.rst)。

- **`arrange_grid` / `arrange_cascade`**(`AC_arrange_grid`、`AC_arrange_cascade`):`snap_window` 移动*一个*窗口、版面规划器只*计算*矩形——这两个把循环补完,接受一组窗口标题并实际把每个匹配的窗口移入网格(自动近正方形,或明确 `rows`/`cols` + `gap`)或对角线层叠。以版面规划器为基础并沿用 `snap_window` 的可注入 `mover`/`screen_size` 接缝,因此完全无头可测;返回移动的窗口数。

## 本次更新 (2026-06-23) — 窗口铺排 / 版面几何规划器

计算应用程序窗口该放在哪里——半边、网格、层叠。完整参考:[`docs/source/Zh/doc/new_features/v133_features_doc.rst`](../docs/source/Zh/doc/new_features/v133_features_doc.rst)。

- **`tile_rect` / `grid_rects` / `cascade_rects`**(`AC_tile_rect`、`AC_grid_rects`、`AC_cascade_rects`):`save/restore_window_layout` 重播*精确*的已存位置、`snap_window` 移动*一个*窗口——没有任何功能能*计算*出全新的多窗口版面。此纯几何规划器在给定屏幕工作区下,返回半边、四分之一、三分之一、R×C 网格与错位层叠的目标矩形,让脚本能以确定性方式排列窗口。返回 `WindowRect`(`.as_tuple()` / `.to_dict()`);`gap` 内缩铺排间距;跨平台且完全无头可测;可与任何窗口移动后端组合。

## 本次更新 (2026-06-23) — 以边缘 / 轮廓定位 UI 元素(免模板)

在从未见过的画面上找出可点击的方框。完整参考:[`docs/source/Zh/doc/new_features/v132_features_doc.rst`](../docs/source/Zh/doc/new_features/v132_features_doc.rst)。

- **`find_shapes` / `find_rectangles`**(`AC_find_shapes`、`AC_find_rectangles`):其他定位器都需要一个寻找对象——模板、颜色或文字。这两个什么都不需要:Canny 边缘检测 + 轮廓提取返回各个形状的边界框(`{x,y,width,height,area,center,aspect}`,由大到小),让脚本能结构性地列举卡片 / 按钮 / 输入框并点击第 N 个。`find_rectangles` 只保留凸四边形,并加上 `aspect_range=(min,max)` 宽高比过滤(`(1.5,8)` 取宽按钮)。可注入 haystack → 无头可测。

## 本次更新 (2026-06-23) — ORB 特征匹配(对旋转 / 缩放 / 主题稳健)

即使目标旋转、缩放或换主题也能找到。完整参考:[`docs/source/Zh/doc/new_features/v131_features_doc.rst`](../docs/source/Zh/doc/new_features/v131_features_doc.rst)。

- **`feature_match`**(`AC_feature_match`):像素模板匹配(`match_template` / `match_masked`)是做像素相关运算,因此目标一旦旋转、以未列出的倍率缩放或重新上色(亮 / 暗主题、hover)就会失效。本功能匹配 ORB *关键点*并拟合 RANSAC 单应矩阵,返回四个投影 `corners`、`center`、`inliers` 内点数与内点比例 `score`。ORB 边界 / patch 尺寸会针对图标大小的模板自动缩小(OpenCV 预设会将其舍弃)。仅用 OpenCV 核心(不需 contrib);可注入 haystack → 无头可测。

## 本次更新 (2026-06-23) — 结构相似度(SSIM)比较

会告诉你*哪里*变了的感知式画面比较。完整参考:[`docs/source/Zh/doc/new_features/v130_features_doc.rst`](../docs/source/Zh/doc/new_features/v130_features_doc.rst)。

- **`ssim_compare` / `ssim_changed_regions`**(`AC_ssim_compare`、`AC_ssim_changed_regions`):像素差(`diff_screenshots`)会因一像素位移而误报;直方图(`detect_drift`)对版面无感。SSIM 是标准视觉回归度量——容忍轻微光照变化、对结构变化敏感。`ssim_compare` 返回 0..1 分数(1.0 = 完全相同);`ssim_changed_regions` 返回哪里移动了的方框。`ignore=[[x,y,w,h]]` 可遮罩即时时钟 / 光标。纯 NumPy + OpenCV(不需 scikit-image);可注入影像配对 → 无头可测。

## 本次更新 (2026-06-23) — 遮罩模板匹配

不论背景如何都能匹配图标。完整参考:[`docs/source/Zh/doc/new_features/v129_features_doc.rst`](../docs/source/Zh/doc/new_features/v129_features_doc.rst)。

- **`match_masked` / `match_masked_all`**(`AC_match_masked`、`AC_match_masked_all`):一般模板匹配会计分*每个*像素,因此从某背景裁切出的图标在不同背景上会匹配失败。本功能只计算你标记为相关的像素——明确的灰阶 `mask`,或 RGBA 模板的 alpha 通道——让透明 /「不在乎」的像素不再拉低分数。返回与计分模板匹配相同的 `Match`(score/center);使用 OpenCV 遮罩 `TM_CCORR_NORMED`,NaN 归零。可注入 haystack → 无头可测。

## 本次更新 (2026-06-23) — 依颜色定位屏幕区域

依颜色找出绿色状态药丸 / 红色横幅。完整参考:[`docs/source/Zh/doc/new_features/v128_features_doc.rst`](../docs/source/Zh/doc/new_features/v128_features_doc.rst)。

- **`find_color_region` / `find_color_regions`**(`AC_find_color_region`):`color_stats` 只描述区域颜色、`assert_pixel` 检查单点——两者都不*定位*彩色区域。本功能将接近目标 RGB(在 `tolerance` 内)的像素遮罩起来,返回相连区块的框(`{x,y,width,height,area,center}`,由大到小)——用于模板脆弱的状态灯、进度填充、错误横幅。可注入 haystack → 无头可测;OpenCV/NumPy 透过 `je_open_cv`。

## 本次更新 (2026-06-23) — 具信心分数的模板匹配

返回分数、搜索多尺度、找出所有出现处的模板匹配。完整参考:[`docs/source/Zh/doc/new_features/v127_features_doc.rst`](../docs/source/Zh/doc/new_features/v127_features_doc.rst)。

- **`match_template` / `match_template_all` / `best_matches` / `TemplateMatch`**(`AC_match_template`、`AC_match_template_all`):既有匹配器(`find_object`)为单一尺度且*丢弃分数*。本功能返回带 `score`/`scale`/`center` 的 `Match`、搜索 `scales` 容忍 DPI/缩放,并以非极大值抑制列举每个出现处。可注入 `haystack`(ndarray/路径/PIL)→ 无头可测;OpenCV/NumPy 透过 `je_open_cv` 依赖。

## 本次更新 (2026-06-23) — 等待窗口标题(正则)

阻塞直到窗口标题符合正则(或消失)。完整参考:[`docs/source/Zh/doc/new_features/v126_features_doc.rst`](../docs/source/Zh/doc/new_features/v126_features_doc.rst)。

- **`wait_until_window_title`**(`AC_wait_window_title`):`wait_for_window` 以子字符串比对且仅等*出现*;`wait_until_window_closed` 为子字符串消失。本功能默认以正则表达式比对(`regex=False` 改子字符串),并可等待标题消失(`present=False`)——例如等标签页导览至 `r".*— Checkout$"`。标题来源可注入、无头可测。

## 本次更新 (2026-06-23) — 表格 / 网格单元格定位

依(行、列)从单元格边界框定位表格单元格。完整参考:[`docs/source/Zh/doc/new_features/v125_features_doc.rst`](../docs/source/Zh/doc/new_features/v125_features_doc.rst)。

- **`cluster_grid` / `locate_cell`**(`AC_grid_cell`):`anchor_locator` 处理成对关系,但无法定位二维网格。给定单元格边界框(来自 `locate_all_image` / `find_text_matches`),本功能将其分群为行(依中心 y 在 `row_tolerance` 内)与列(依中心 x),并返回 0 起算 `(row, col)` 单元格的中心——可直接点击。纯分群、完全无头可测。

## 本次更新 (2026-06-23) — 锚点序数与全部定位

挑选第 N 个锚点相对匹配,或列举全部。完整参考:[`docs/source/Zh/doc/new_features/v124_features_doc.rst`](../docs/source/Zh/doc/new_features/v124_features_doc.rst)。

- **`anchor_locate(..., ordinal=N)` / `anchor_locate_all`**(`AC_anchor_locate` ordinal、`AC_anchor_locate_all`):`anchor_locate` 总是返回单一最近的匹配——无法取「标题下方第 2 行」或列出每一行。本功能加入 1 起算的 `ordinal` 选择器(向后兼容;`ordinal=1` 即最近)与返回依距离排序所有匹配的 `anchor_locate_all`——表格/列表行选取的基础元件。纯排序核心、确定。

## 本次更新 (2026-06-23) — 在动作组中持续按住修饰键

在多个动作之间持续按住 ctrl/shift,即使出错也会放开。完整参考:[`docs/source/Zh/doc/new_features/v123_features_doc.rst`](../docs/source/Zh/doc/new_features/v123_features_doc.rst)。

- **`hold_modifiers` / `plan_with_modifiers`**(`AC_with_modifiers`):`hotkey` 会立即放开按键——先前无法在多个独立动作之间持续按住修饰键(shift 连点范围选取、ctrl 连点多选)并保证放开。`hold_modifiers` 是 context manager,进入时按下、离开时(在 `finally`)以反向放开,因此不会泄漏;`plan_with_modifiers` 为纯计划。可注入 sink、确定。

## 本次更新 (2026-06-23) — Unicode 文本输入(emoji / CJK)

输入 `write` 无法处理的任何 Unicode(emoji / CJK / 重音)。完整参考:[`docs/source/Zh/doc/new_features/v122_features_doc.rst`](../docs/source/Zh/doc/new_features/v122_features_doc.rst)。

- **`type_unicode` / `plan_paste` / `unicode_code_units`**(`AC_type_unicode`):`write` 通过虚拟键表输入,对 emoji/CJK/许多重音字会*抛异常*。`type_unicode` 以设定剪贴板再粘贴(`modifier` ctrl/command)可靠地输入任何文本。`unicode_code_units` 将文本拆成 UTF-16 码元(代理对)供 KEYEVENTF_UNICODE 后端使用。纯计划 + 可注入 sink、确定。

## 本次更新 (2026-06-23) — 等待区域颜色

阻塞直到某颜色填满(或离开)屏幕区域。完整参考:[`docs/source/Zh/doc/new_features/v121_features_doc.rst`](../docs/source/Zh/doc/new_features/v121_features_doc.rst)。

- **`wait_until_color`**(`AC_wait_color`):`wait_for_pixel` 精确比对单点、`wait_until_pixel_changes` 检测单点任何变化——两者都无法等「状态灯变绿」/「进度条填满」/「红色横幅消失」。本功能计数区域中接近 `target_rgb`(在 `tolerance` 内)的像素,当比例越过 `min_fraction`(或 `present=False` 时低于)即成功。可注入 sampler、无头可测。纯标准库。

## 本次更新 (2026-06-23) — 相对鼠标移动

从当前位置将指针位移一个增量。完整参考:[`docs/source/Zh/doc/new_features/v120_features_doc.rst`](../docs/source/Zh/doc/new_features/v120_features_doc.rst)。

- **`move_mouse_relative` / `relative_target`**(`AC_move_mouse_relative`):鼠标 wrapper 只有绝对的 `set_mouse_position`——没有给相对指针 / 画布 / FPS 应用与渐进式拖曳用的 `moveRel(dx, dy)`。本功能读取实时位置并依增量移动;`relative_target` 为纯算术,getter/setter 可注入以供无头测试。纯标准库、确定。

## 本次更新 (2026-06-23) — 按住按键 / 自动重复

按住一个键一段时间,或以固定频率自动重复。完整参考:[`docs/source/Zh/doc/new_features/v119_features_doc.rst`](../docs/source/Zh/doc/new_features/v119_features_doc.rst)。

- **`hold_key` / `plan_key_hold`**(`AC_hold_key`):`type_keyboard` 是瞬间按下+放开——先前没有「按住此键 N 秒」(游戏移动、按住滚动)或「每秒送 R 次」(自动重复)。`plan_key_hold` 建立确定性操作计划(按下/等待/放开,或为 `rate_hz` 产生 N 个间隔按键事件);`hold_key` 将等待导向可注入的 `sleep`、按键导向可注入的 `sink`。纯计划、确定。

## 本次更新 (2026-06-23) — 等待消失(阻塞式 vanish 等待)

阻塞直到转圈圈 / toast / 对话框消失。完整参考:[`docs/source/Zh/doc/new_features/v118_features_doc.rst`](../docs/source/Zh/doc/new_features/v118_features_doc.rst)。

- **`wait_until_gone` / `wait_until_image_gone` / `wait_until_text_gone`**(`AC_wait_image_gone`、`AC_wait_text_gone`):`wait_for_image`/`wait_for_text` 只阻塞到某物*出现*,`observer` 则以异步回调在消失时触发——先前没有*阻塞式*的「等到此图像/文本消失再继续」。通用的 `wait_until_gone` 接受任意谓词(可无头测试);图像/文本辅助函数从定位函数建立。`gone_for_s` 可消抖。返回 `WaitOutcome`。纯标准库。

## 本次更新 (2026-06-23) — 清空再输入字段

可靠地设定文本字段的值(Playwright 的 `fill` 惯用法)。完整参考:[`docs/source/Zh/doc/new_features/v117_features_doc.rst`](../docs/source/Zh/doc/new_features/v117_features_doc.rst)。

- **`set_field_text` / `plan_field_set`**(`AC_set_field_text`):先前没有单一的「聚焦 → 清空 → 设值」基本元件,且 `write` 对 emoji/CJK 会抛异常。本功能清空字段(全选 + 删除)后再输入文本——可选择通过剪贴板(`paste=True`),这是 `write` 无法处理之 Unicode 的安全途径。`modifier` 为平台命令键(`ctrl`/`command`)。纯计划 + 可注入 sink、确定。

## 本次更新 (2026-06-22) — 多路径点鼠标手势

让指针沿着路径点折线移动或拖曳。完整参考:[`docs/source/Zh/doc/new_features/v116_features_doc.rst`](../docs/source/Zh/doc/new_features/v116_features_doc.rst)。

- **`plan_path` / `move_along_path` / `drag_path` / `path_easings`**(`AC_move_along_path`、`AC_drag_path`):`humanize` 与 `tween_drag` 只在单一起点→终点之间插值——先前无法驱动任意的路径点链(签名、框选、多停靠点拖曳)并在整段路径中按住按键。`plan_path` 为纯缓动点运算(重用 `tween_drag` 的缓动、交接点去重);移动/拖曳通过可注入的 sink 派发以供无头测试。纯标准库、确定。

## 本次更新 (2026-06-22) — 校验位算法

计算/验证 Luhn、Verhoeff、Damm 与 ISO 7064 MOD 97-10 校验位。完整参考:[`docs/source/Zh/doc/new_features/v115_features_doc.rst`](../docs/source/Zh/doc/new_features/v115_features_doc.rst)。

- **`luhn_validate` / `luhn_check_digit` / `verhoeff_*` / `damm_*` / `mod97_10_*`**(`AC_checksum_validate`、`AC_checksum_digit`):`pii_text` 以正则检测卡号/IBAN 形状、`data_quality` 做正则验证,但没有任何功能计算或验证*校验位*。本功能加入多数标识符背后的四种方案(卡号/IMEI、身份证号、IBAN)——`identifier_validate` 所依据的共用引擎。纯标准库、确定。

## 本次更新 (2026-06-22) — 移动平均平滑

平滑噪声值序列。完整参考:[`docs/source/Zh/doc/new_features/v102_features_doc.rst`](../docs/source/Zh/doc/new_features/v102_features_doc.rst)。

## 本次更新 (2026-06-22) — GNU gettext 目录 I/O(.po / .mo)

读取/编译事实标准翻译格式。完整参考:[`docs/source/Zh/doc/new_features/v114_features_doc.rst`](../docs/source/Zh/doc/new_features/v114_features_doc.rst)。

- **`parse_po` / `read_mo` / `GettextCatalog` / `parse_po_file` / `read_mo_file`**(`AC_gettext_translate`、`AC_gettext_ngettext`):本项目能伪在地化并渲染 ICU 消息,却无法读取 GNU gettext `.po`/`.mo`。本功能解析 `.po`(上下文、复数、以 `gettext.c2py` 处理 `Plural-Forms` 标头)、编译可被 Python 内建 `gettext.GNUTranslations` 载入的标准 `.mo`,并提供 `gettext`/`ngettext`/`pgettext`。纯标准库、确定。

## 本次更新 (2026-06-22) — ICU-lite MessageFormat(复数 / 选择)

渲染依数量变化的在地化消息。完整参考:[`docs/source/Zh/doc/new_features/v113_features_doc.rst`](../docs/source/Zh/doc/new_features/v113_features_doc.rst)。

- **`format_message` / `plural_category` / `ordinal_category`**(`AC_format_message`):`i18n_test.check_catalog` 只比较占位符集合、`interpolate` 只做扁平 `${var}`——两者都无法渲染 `"{count, plural, one {# item} other {# items}}"`。本功能实作多数应用会用到的 ICU MessageFormat 子集:`select`、`plural`、`selectordinal` 搭配 CLDR 类别、优先于类别的精确 `=N` 选择器、`#` 数量、`offset:`、嵌套与单引号转义。复数规则可注入。纯标准库、确定。

## 本次更新 (2026-06-22) — 区域感知列表格式化

依某语言的期望串接项目(「A、B and C」)。完整参考:[`docs/source/Zh/doc/new_features/v112_features_doc.rst`](../docs/source/Zh/doc/new_features/v112_features_doc.rst)。

- **`format_list`**(`AC_format_list`):直接 `", ".join` 只会得到「A, B, C」,没有「and/or」也没有在地化。本功能实作 CLDR 列表样式组合,支援连接(and)/选择(or)/单位(unit)样式,并依区域提供连接词与序列逗号规则(`en`/`es`/`fr`/`de`/`pt`)——`format_list(["a","b","c"])` → 「a, b, and c」,`locale="es"` → 「a, b y c」。纯标准库、确定。

## 本次更新 (2026-06-22) — 双向文字 QA(Trojan-Source 扫描)

抓出隐形的 Unicode 方向格式控制(RTL QA + Trojan-source)。完整参考:[`docs/source/Zh/doc/new_features/v111_features_doc.rst`](../docs/source/Zh/doc/new_features/v111_features_doc.rst)。

- **`detect_bidi_issues` / `bidi_controls` / `is_bidi_balanced` / `base_direction` / `is_trojan_source` / `strip_bidi_controls` / `has_bidi_controls`**(`AC_bidi_check`、`AC_bidi_strip`):`confusables` 抓相似字符,但双向控制(LRO/RLO/PDF、隔离、标记)可悄悄改变呈现顺序——既是 RTL QA 缺口,也是「Trojan Source」攻击(CVE-2021-42574)。本功能列出控制字符、检查嵌套平衡、推断基底方向,并标记重排格式。纯标准库(`unicodedata`)、确定。

## 本次更新 (2026-06-22) — 可读性评分

评估文字有多难读;以阅读年级把关生成的文案。完整参考:[`docs/source/Zh/doc/new_features/v110_features_doc.rst`](../docs/source/Zh/doc/new_features/v110_features_doc.rst)。

- **`flesch_reading_ease` / `flesch_kincaid_grade` / `gunning_fog` / `smog_index` / `automated_readability_index` / `readability_report` / `readability_stats` / `count_syllables`**(`AC_readability_report`):文字工具能正规化、比对与排名文字,却从未评估*难度*。本功能在确定性分词器与音节启发式之上加入经典英文可读性公式,让测试能断言画面消息或标签落在目标阅读年级内。纯标准库(`re`/`math`)、确定。

## 本次更新 (2026-06-22) — 易混淆字符 / 同形异义字检测

抓出 Unicode 视觉仿冒(IDN 同形异义字钓鱼、仿冒标签)。完整参考:[`docs/source/Zh/doc/new_features/v109_features_doc.rst`](../docs/source/Zh/doc/new_features/v109_features_doc.rst)。

- **`confusable_skeleton` / `is_confusable` / `detect_homoglyphs` / `is_mixed_script` / `scripts_of`**(`AC_confusable_scan`、`AC_confusable_compare`):西里尔字母 `"а"` 与拉丁字母 `"a"` 在像素上相同,因此 `"pаypal"` 读来是 `"paypal"` 却比较不相等。参照 Unicode TR39,本功能将易混淆字折叠为原型骨架(骨架相同即相符),并标记混用文字系统的令牌。纯标准库(`unicodedata`)、确定。

## 本次更新 (2026-06-22) — 区域感知字符串排序

依某语言读者的期望排序字符串。完整参考:[`docs/source/Zh/doc/new_features/v108_features_doc.rst`](../docs/source/Zh/doc/new_features/v108_features_doc.rst)。

- **`sort_strings` / `collation_compare` / `collation_key`**(`AC_collation_sort`、`AC_collation_compare`):Python 默认的 `sorted` 是码位顺序,因此 `"Z" < "a"`,而 `"ä"` 离 `"a"` 很远。本 Unicode-Collation-lite 键先依基底字母、再依变音符号(次层)、再依大小写(三层)排序,并可用 `tailoring` 字母表让瑞典文将 `å ä ö` 排在 `z` 之后。纯标准库(`unicodedata`)、跨平台确定——不像 `locale.strxfrm`。

## 本次更新 (2026-06-22) — 事务型 Outbox

持久化缓冲事件并以至少一次传递排空。完整参考:[`docs/source/Zh/doc/new_features/v107_features_doc.rst`](../docs/source/Zh/doc/new_features/v107_features_doc.rst)。

- **`Outbox`**(`AC_outbox_enqueue`、`AC_outbox_pending`):`events.cloud_events` 同步发送且无持久化——当机或网络抖动就会丢失事件。Outbox 先持久化每个事件,再通过注入的 sink 以至少一次传递 `drain` 待传递项目:sink 失败时项目维持待传递以供重试,直到 `max_attempts`,之后列为死信。`save` / `load` 让事件能跨重启存活。纯标准库、确定。

## 本次更新 (2026-06-22) — 乐观并发版本存储

只在版本未变时更新(compare-and-swap / If-Match)。完整参考:[`docs/source/Zh/doc/new_features/v106_features_doc.rst`](../docs/source/Zh/doc/new_features/v106_features_doc.rst)。

- **`VersionedStore` / `VersionConflict` / `if_match_header` / `check_if_match`**(`AC_cas_put`、`AC_cas_get`):`http_conditional` 以 ETag 做读取缓存,但从不用于写入并发。本地 compare-and-swap 存储仅在 `expected_version` 相符时 `put`(过时写入抛出 `VersionConflict`)、递增单调版本,并桥接到 HTTP `If-Match` —— ETag 故事的写入面。纯标准库、确定。

## 本次更新 (2026-06-22) — 逐流序号间隙检测

按序号检测遗漏/乱序/重复的消息。完整参考:[`docs/source/Zh/doc/new_features/v105_features_doc.rst`](../docs/source/Zh/doc/new_features/v105_features_doc.rst)。

- **`SequenceTracker`**(`AC_sequence_observe`):没有东西追踪每个流的单调序号。`observe(stream, seq)` 将每个分类为 `ok` / `duplicate` / `gap`(附 `missing` 序号)/ `reorder`(迟到填补间隙),并提供 `gaps` 与 `high_water`。与 `dedup_window` 互补。纯标准库、确定。

## 本次更新 (2026-06-22) — 时间窗口去重

在 TTL 窗口内丢弃重复/重送的消息。完整参考:[`docs/source/Zh/doc/new_features/v104_features_doc.rst`](../docs/source/Zh/doc/new_features/v104_features_doc.rst)。

- **`DedupWindow`**(`AC_dedup_check`):`work_queue` 只对进行中引用去重,因此已完成的引用会重新入列、重送的 webhook 会重复处理。本滑动窗口收件箱对消息 id 做 `check_and_mark` —— 首次返回 `True`、`ttl_s` 窗口内重复返回 `False` —— 把至少一次投递转换成窗口内恰好一次。可注入时钟、大小有界。纯标准库、确定。

## 本次更新 (2026-06-22) — 幂等键存储

副作用只执行一次,重试时重播其响应。完整参考:[`docs/source/Zh/doc/new_features/v103_features_doc.rst`](../docs/source/Zh/doc/new_features/v103_features_doc.rst)。

- **`IdempotencyStore` / `request_fingerprint` / `IdempotencyConflict`**(`AC_idempotency_begin`、`AC_idempotency_complete`):`RetryPolicy` 重试会重跑,`work_queue` 只对进行中引用去重 —— 没有东西缓存第一次结果。本 Stripe 风格存储为某键返回 `new`/`in_progress`/`completed`、重播已存储响应、指纹冲突时抛出异常,并支持可注入时钟 TTL + JSON 持久化。纯标准库、确定。

- **`sma` / `wma` / `ewma` / `rolling`**(`AC_sma`、`AC_ewma`):`stats.describe` 汇总整个样本,`timeseries` 把计数器滚成速率,但没有东西能平滑噪声信号。本功能加入尾端简单/加权/指数加权移动平均与通用滚动归约器,全部返回与输入时间线对齐的等长 list。纯标准库、确定。

## 本次更新 (2026-06-22) — 单序列异常检测

标记单一实时度量序列中的尖峰。完整参考:[`docs/source/Zh/doc/new_features/v101_features_doc.rst`](../docs/source/Zh/doc/new_features/v101_features_doc.rst)。

- **`detect_anomalies` / `mad_anomalies` / `zscore_anomalies` / `ewma_control`**(`AC_detect_anomalies`):`data_drift` 是两批次分布偏移,`slo.burn_alerts` 只对预算燃烧设门槛 —— 都无法指出单一序列中*哪个*值异常。本功能以稳健 MAD(modified z-score)、纯 z-score 与 EWMA 控制图(可选 in-control 基准)标记离群值 —— `{index, value, score, is_anomaly}` 记录。纯标准库、确定。

## 本次更新 (2026-06-22) — 近似重复文本检测(SimHash / MinHash)

为文本生成指纹以大规模找近似重复。完整参考:[`docs/source/Zh/doc/new_features/v100_features_doc.rst`](../docs/source/Zh/doc/new_features/v100_features_doc.rst)。

- **`simhash` / `near_duplicates` / `minhash_signature` / `minhash_similarity`**(`AC_simhash`、`AC_near_duplicates`):`fuzzy_dedupe` 是 O(n²) 成对且无稳定指纹,`image_dedup` 只哈希像素。本功能加入文本对应 —— SimHash(Hamming 距离近似重复聚类)与 MinHash(估计 Jaccard),使用固定 `blake2b` 哈希取得确定的指纹。可搭配 `normalize_text`。纯标准库。

## 本次更新 (2026-06-22) — 字符串距离相似度量

匹配打字错误与重排 token。完整参考:[`docs/source/Zh/doc/new_features/v99_features_doc.rst`](../docs/source/Zh/doc/new_features/v99_features_doc.rst)。

- **`levenshtein` / `damerau_levenshtein` / `jaro` / `jaro_winkler` / `jaccard` / `dice` / `similarity`**(`AC_text_similarity`):`fuzzy` 只提供 difflib 的 gestalt ratio。本功能补上它缺少的编辑距离与 token 集合度量 —— Jaro-Winkler(短标签标准)、Damerau(转置感知)、字符 n-gram Jaccard/Dice —— 并提供统一的 `similarity()` 把每个度量规范化到 `[0, 1]`。可搭配 `normalize_text`。纯标准库、确定。

## 本次更新 (2026-06-22) — 时间序列变换

把计数器转成速率;降采样与重采样。完整参考:[`docs/source/Zh/doc/new_features/v98_features_doc.rst`](../docs/source/Zh/doc/new_features/v98_features_doc.rst)。

- **`ts_rate` / `ts_irate` / `ts_increase` / `ts_delta` / `ts_downsample` / `ts_resample`**(`AC_ts_rate`、`AC_ts_downsample`):`observability` 计数器只存当前值(无处可把计数器转速率),`cost_telemetry` 只以天分桶。本功能在 `(timestamp, value)` 序列上加入 Prometheus 风格、具重置感知的 rate/increase/delta、tumbling-bucket 降采样(avg/sum/min/max/first/last/count)与网格重采样(last/linear/none)。不读 wall clock、确定。纯标准库。

## 本次更新 (2026-06-22) — Unicode 文本规范化与 Slug

在 fuzzy/search/OCR 匹配前规范化文本。完整参考:[`docs/source/Zh/doc/new_features/v97_features_doc.rst`](../docs/source/Zh/doc/new_features/v97_features_doc.rst)。

- **`normalize_text` / `deaccent` / `slugify` / `normalize_quotes` / `fold_whitespace`**(`AC_normalize_text`、`AC_slugify`):`fuzzy` 与 `search_index.tokenize` 只做小写,OCR 匹配只做 `.lower()`+子串,因此 `"Café"`(NFC)、`"Café"`(NFD)、`"cafe"` 会匹配不相等。本功能补上缺少的规范化层(NFKC + casefold + 空白折叠、去重音、智能引号映射、ASCII slug)。纯标准库(`unicodedata`)、确定。

## 本次更新 (2026-06-22) — JSON-Schema 兼容性检查

把结构变更分类为 backward/forward/full。完整参考:[`docs/source/Zh/doc/new_features/v96_features_doc.rst`](../docs/source/Zh/doc/new_features/v96_features_doc.rst)。

- **`check_compatibility` / `diff_schemas` / `is_backward_compatible` / `is_forward_compatible` / `is_full_compatible`**(`AC_check_compatibility`):我们能依结构验证并生成结构,但无法回答「旧消费者是否仍能读新数据?」。本功能依 Confluent/Avro backward/forward/full 规则,在对象子集上分类变更(新增必填字段、移除字段、收窄/放宽类型、enum 增减)。纯标准库、确定。

## 本次更新 (2026-06-22) — 具类型的配置结构

把配置验证成具类型的对象。完整参考:[`docs/source/Zh/doc/new_features/v95_features_doc.rst`](../docs/source/Zh/doc/new_features/v95_features_doc.rst)。

- **`ConfigSchema` / `ConfigField` / `validate_config` / `coerce`**(`AC_validate_config`):`assets._coerce` 只转换单一值,`json_schema` 只验证结构,但没有东西把已解析配置 dict 绑定成具类型对象并做必填强制与选项约束。本功能转换类型(`str`/`int`/`float`/`bool`)、应用默认、强制必填/选项,返回 `{ok, config, errors}` —— 标准库版 pydantic-settings。纯标准库、确定。

## 本次更新 (2026-06-22) — OTLP/JSON Span 导出

以 collector 摄取的格式导出 span。完整参考:[`docs/source/Zh/doc/new_features/v94_features_doc.rst`](../docs/source/Zh/doc/new_features/v94_features_doc.rst)。

- **`spans_to_otlp` / `attributes_to_otlp` / `write_otlp`**(`AC_spans_to_otlp`):`agent_trace.to_otel` 返回扁平 dict,并非有效 OTLP/JSON(没有 resourceSpans/scopeSpans 嵌套、时间不是 uint64 字符串)。本功能把 span 包进正确封套,含 hex ID、uint64 字符串时间,以及 OTLP `KeyValue` 属性编码 —— OpenTelemetry collector file exporter 读取的格式。与 `trace_context` 搭配。纯标准库、确定。

## 本次更新 (2026-06-22) — 标准日志行与结构化日志

每次执行一行宽事件,并带 trace 关联。完整参考:[`docs/source/Zh/doc/new_features/v93_features_doc.rst`](../docs/source/Zh/doc/new_features/v93_features_doc.rst)。

- **`CanonicalLogLine` / `JSONLogFormatter` / `bind_trace_context`**(`AC_canonical_log`):`logging_instance` 输出固定的管线分隔字符串,没有 JSON 也没有 trace/span 字段。本功能加入 Stripe 风格的标准日志行(字段累积器 + 可注入时钟的 `timer`)以及携带 `trace_id`/`span_id` 的 JSON `logging.Formatter` —— 与 `trace_context` 对应的 log-trace 关联。纯标准库、确定。

## 本次更新 (2026-06-22) — 条件式 HTTP 请求与缓存验证子

跳过重新下载未变更的资源(ETag / 304)。完整参考:[`docs/source/Zh/doc/new_features/v92_features_doc.rst`](../docs/source/Zh/doc/new_features/v92_features_doc.rst)。

- **`store_validators` / `conditioned_call` / `is_fresh` / `parse_cache_control` / `is_not_modified`**(`AC_parse_cache_control`、`AC_store_validators`):`http_request` 从不发 `If-None-Match`/`If-Modified-Since` 也不读 `Cache-Control`,因此每次轮询都重新下载。本功能提取验证子、解析 `Cache-Control`(max-age/no-store/…)、以明确 age 判定新鲜度、为下一个请求加上条件标头,并检测 `304 Not Modified`。纯标准库、确定。

## 本次更新 (2026-06-22) — Cookie Jar(HTTP 会话携带)

跨 HTTP 调用携带会话。完整参考:[`docs/source/Zh/doc/new_features/v91_features_doc.rst`](../docs/source/Zh/doc/new_features/v91_features_doc.rst)。

- **`CookieJar` / `parse_set_cookie`**(`AC_cookie_header`、`AC_parse_set_cookie`):`http_request` 无状态 —— 没有会话 cookie 在调用间延续,login-then-call 流程无法在无头情况下携带会话。本功能把 `Set-Cookie` 标头解析进 jar、构建 `Cookie` 请求标头,并以 JSON 存/读 jar(`Max-Age<=0`/空值时清除)。纯标准库、确定。

## 本次更新 (2026-06-22) — HTTP 内容协商与解压

构建 `Accept` 标头并解码 gzip/deflate。完整参考:[`docs/source/Zh/doc/new_features/v90_features_doc.rst`](../docs/source/Zh/doc/new_features/v90_features_doc.rst)。

- **`build_accept` / `build_accept_encoding` / `parse_quality_values` / `decode_body` / `negotiated_call`**(`AC_decode_body`、`AC_parse_quality_values`):`urllib`/`http_request` 从不设置 `Accept-Encoding` 也不解码 `Content-Encoding`,压缩内文以原始形式抵达。本功能加入 `Accept`/`Accept-Encoding` 构建器、q-value 解析器(按品质排序),以及 gzip/deflate(含 raw deflate)解码。排除 Brotli(非标准库)。纯标准库、确定。

## 本次更新 (2026-06-22) — multipart/form-data 构建与解析

构建文件上传内文。完整参考:[`docs/source/Zh/doc/new_features/v89_features_doc.rst`](../docs/source/Zh/doc/new_features/v89_features_doc.rst)。

- **`build_multipart` / `parse_multipart` / `MultipartFile`**(`AC_build_multipart`、`AC_parse_multipart`):`http_request` 只发 JSON/原始 —— 没有文件上传,且解析 multipart 的标准库 `cgi` 已在 3.13 移除。本功能以可注入的 boundary(字节稳定)从文本字段与文件组装 `multipart/form-data` 内文,并能解析回 `{fields, files}`。纯标准库、确定。

## 本次更新 (2026-06-22) — 配置与日志的机密脱敏

在记录或导出前脱敏机密。完整参考:[`docs/source/Zh/doc/new_features/v88_features_doc.rst`](../docs/source/Zh/doc/new_features/v88_features_doc.rst)。

- **`redact_config` / `redact_secret_text`**(`AC_redact_config`、`AC_redact_secret_text`):`utils/redaction` 只模糊截图,`secrets_scan` 只*检测* —— 两者都不返回脱敏后的副本。本功能重用 `secrets_scan` 检测器(键名模式、AWS/bearer 格式、高熵)返回配置结构的脱敏深层副本,并脱敏自由文本日志行中看似机密的 token(保留周围文本)。vault 引用(`${secrets.*}`)保持不变。纯标准库、确定。

## 本次更新 (2026-06-22) — RFC 8288 Link 标头与分页

解析 `Link` 标头并跟随 `rel="next"`。完整参考:[`docs/source/Zh/doc/new_features/v87_features_doc.rst`](../docs/source/Zh/doc/new_features/v87_features_doc.rst)。

- **`parse_link_header` / `next_url` / `links_by_rel` / `paginate`**(`AC_parse_link_header`、`AC_next_url`):分页的 REST API 返回 `Link: <...>; rel="next"`,但没有东西解析它。本功能解析该标头(含逗号的引号值、多个链接)、按关系索引,`paginate` 通过注入的 `fetch`(传输/卡带)跟随 `rel="next"`,上限为 `max_pages`。纯标准库、确定。

## 本次更新 (2026-06-22) — 参照完整性检查

跨数据表的外键、唯一键、accepted-values 与行数检查。完整参考:[`docs/source/Zh/doc/new_features/v86_features_doc.rst`](../docs/source/Zh/doc/new_features/v86_features_doc.rst)。

- **`check_foreign_key` / `check_unique_key` / `check_accepted_values` / `check_row_count`**(`AC_check_foreign_key`、`AC_check_unique_key`、`AC_check_accepted_values`、`AC_check_row_count`):`validate_rows` 是单行、单表(其 `unique` 只在单批次内去重)。本功能补上 dbt 风格通用检查 —— 跨两表的父子外键、单一/复合键唯一性、accepted-values、行数范围 —— 作用于 `load_rows`/`query_sqlite` 的数据行。纯标准库、确定。

## 本次更新 (2026-06-22) — URI-Scheme 值引用

在配置中存储指针而非机密。完整参考:[`docs/source/Zh/doc/new_features/v85_features_doc.rst`](../docs/source/Zh/doc/new_features/v85_features_doc.rst)。

- **`resolve_ref` / `resolve_refs_in` / `is_ref` / `RefResolver`**(`AC_resolve_ref`、`AC_resolve_refs`):`interpolate` 只写死 `${secrets.NAME}`,`AssetStore` 引用仅限 vault 名称 —— 没有通用的读取时间接。本功能解析 `env://VAR`、`file://path`(可选 `base_dir` 防穿越保护)与 `secret://name`(可注入解析器或 governance broker),并遍历嵌套结构解析每个引用。env 读取器 / secret 解析器 / 基目录均可注入。纯标准库、确定。

## 本次更新 (2026-06-21) — W3C Baggage 传播

跨 HTTP 携带横切键值上下文。完整参考:[`docs/source/Zh/doc/new_features/v84_features_doc.rst`](../docs/source/Zh/doc/new_features/v84_features_doc.rst)。

- **`Baggage` / `parse_baggage` / `format_baggage` / `inject_baggage` / `extract_baggage`**(`AC_baggage_parse`、`AC_baggage_format`):`trace_context` 携带 trace/span 身份,但没有东西传播横切上下文(`run_id`/`tenant`/`experiment`)。本功能实现 W3C Baggage 标头 —— percent-encoded 的 `key=value` 列表 —— 以不可变的 `Baggage`(set/remove 返回新实例)与不分大小写的 inject/extract。与 `trace_context` 搭配。纯标准库、确定。

## 本次更新 (2026-06-21) — 数据集差异(数据行变更报告)

按键比对两份表格式提取。完整参考:[`docs/source/Zh/doc/new_features/v83_features_doc.rst`](../docs/source/Zh/doc/new_features/v83_features_doc.rst)。

- **`diff_rows` / `cell_changes` / `summarize_diff`**(`AC_diff_rows`、`AC_cell_changes`):框架能比对画面/快照,但没有任何东西能按键比对两个**表格式**数据行集合。本功能为两侧建键索引并报告 `{added, removed, changed, unchanged}`(changed 带 `{key, old, new}`),展开逐列 `{key, column, old, new}` 变更,并统计每个分类。支持复合键;重复键以最后一行为准。纯标准库、确定。

## 本次更新 (2026-06-21) — 分布漂移检测

检查今天的数据形状是否与基准一致。完整参考:[`docs/source/Zh/doc/new_features/v82_features_doc.rst`](../docs/source/Zh/doc/new_features/v82_features_doc.rst)。

- **`psi` / `ks_two_sample` / `categorical_drift` / `detect_drift`**(`AC_detect_drift`、`AC_categorical_drift`):`stats` 有 A/B 实验检定,但没有 Population Stability Index,也没有针对 reference-vs-current 分布的 KS 双样本检定。本功能加入 PSI(分位分箱的 log-ratio)、KS 统计量与 Kolmogorov p 值,以及类别卡方 + total-variation 摘要 —— 与 `data_profile` 搭配。`detect_drift` 给出一次性的 `{psi, drifted, ks}` 判定。纯标准库、确定。

## 本次更新 (2026-06-21) — 分层配置解析器

以 `defaults < file < env < CLI` 优先级组合配置。完整参考:[`docs/source/Zh/doc/new_features/v81_features_doc.rst`](../docs/source/Zh/doc/new_features/v81_features_doc.rst)。

- **`LayeredConfig` / `deep_merge` / `SourceTrace`**(`AC_resolve_config`、`AC_explain_config`):`json_patch.merge_patch` 只合并两份文档,`config_sync` 是 last-write-wins,`AssetStore` 是每环境扁平 —— 都无法组成有序优先级堆叠并深度合并,也无法报告每个键由哪层胜出。`add_layer(name, mapping, priority)` 后 `resolve()` 深度合并(嵌套 dict 递归、标量/list 替换);`explain("db.host")` 标明胜出层。各层由调用端提供(env 由外部传入,绝不隐含 `os.environ`)。纯标准库、确定。

## 本次更新 (2026-06-21) — Server-Sent Events (SSE) 客户端解析器

消费 `text/event-stream` 响应。完整参考:[`docs/source/Zh/doc/new_features/v80_features_doc.rst`](../docs/source/Zh/doc/new_features/v80_features_doc.rst)。

- **`parse_event_stream` / `SSEParser` / `SSEEvent`**(`AC_parse_sse`):MCP 的 HTTP 传输会发出 SSE,但没有任何东西消费它 —— 一个流式的 LLM/agent/chatops 端点会让 `http_request` 拿到原始 blob。本功能实现 WHATWG event-stream 解析算法(`event`/`data`/`id`/`retry`、注释、前导空格规则、空行派发),并提供逐块的增量 `feed` 与一次性的 `parse_event_stream`。纯标准库、完全确定。

## 本次更新 (2026-06-21) — Dotenv (.env) 解析

把 12-factor `.env` 文件读进配置。完整参考:[`docs/source/Zh/doc/new_features/v79_features_doc.rst`](../docs/source/Zh/doc/new_features/v79_features_doc.rst)。

- **`parse_dotenv` / `load_dotenv` / `dotenv_values` / `dump_dotenv`**(`AC_parse_dotenv`、`AC_load_dotenv`):`load_vars_from_json` 载入扁平 JSON,但没有任何东西读取 de-facto 的 `.env` 文件。本功能把 `KEY=VALUE` 行(`export` 前缀、单/双引号、`\n`/`\t` 转义、行内注释)解析成纯 dict —— 不依赖 `python-dotenv`。载入器合并进调用端提供的 mapping 而非变动 `os.environ`,因此安全且确定。纯标准库。

## 本次更新 (2026-06-21) — RFC 9457 Problem Details 解析

从 HTTP 响应读取标准化的 API 错误。完整参考:[`docs/source/Zh/doc/new_features/v78_features_doc.rst`](../docs/source/Zh/doc/new_features/v78_features_doc.rst)。

- **`parse_problem` / `is_problem` / `raise_for_problem` / `ProblemDetails`**(`AC_parse_problem`):`http_request` 返回的非 2xx 内文未经解析,因此流程与 `assert_http` 无法以结构化方式读取标准化的 API 错误。本功能解析 RFC 9457 `application/problem+json` 文档 —— 已注册的 `type`/`title`/`status`/`detail`/`instance` 成员加上 vendor 扩展字段 —— 对非 problem 响应返回 `None`,或抛出 `HttpProblemError`。纯标准库、完全确定。

## 本次更新 (2026-06-21) — 数据剖析与结构推断

扫描数据行集合并提出验证结构。完整参考:[`docs/source/Zh/doc/new_features/v77_features_doc.rst`](../docs/source/Zh/doc/new_features/v77_features_doc.rst)。

- **`profile_rows` / `infer_schema`**(`AC_profile_rows`、`AC_infer_schema`):`validate_rows` 消费手写结构,`stats.describe` 只汇总单一数值列表 —— 没有任何东西扫描整个数据行集合。本功能剖析每列(空值比例、基数、推断类型、最常见值、数值 min/max/mean)并推断出 `validate_rows` 兼容结构(无空值即 required、相异即 unique、数值边界)—— 馈入既有验证器的剖析步骤。纯标准库、完全确定。

## 本次更新 (2026-06-21) — W3C Trace Context 传播

跨 HTTP 边界关联 span 与日志。完整参考:[`docs/source/Zh/doc/new_features/v76_features_doc.rst`](../docs/source/Zh/doc/new_features/v76_features_doc.rst)。

- **`SpanContext` / `new_root_context` / `child_context` / `inject_context` / `extract_context`**(`AC_trace_inject`、`AC_trace_extract`):既有追踪器与 `agent_trace` 的 span 不带 ID,因此一次 HTTP 调用一端的 span 无法与它在另一端触发的工作关联。本功能实现 W3C Trace Context 标准 —— 生成/解析/传播 `traceparent` + `tracestate` 标头(version-`00`,拒绝格式不符/全零 ID),并以可注入 RNG 让测试中的 ID 确定。纯标准库。

## 本次更新 (2026-06-21) — HTTP 录制与重播卡带

在 CI 中重跑 API 流程,无需在线服务器。完整参考:[`docs/source/Zh/doc/new_features/v75_features_doc.rst`](../docs/source/Zh/doc/new_features/v75_features_doc.rst)。

- **`Cassette` / `CassetteMissError`**(`AC_http_replay`):HTTP 客户端把 `urllib` 传输写死,因此驱动真实 API 的流程无法离线重跑。客户端现在开放 `build_call` / `urllib_transport` 接缝,本功能加入 VCR 风格卡带 —— `replay` 为相符请求返回已录制响应(纯粹、不联网,对 CI 最有价值的一半),`recording_transport` 则是在实际传输之上的薄薄转送。可按 `method`/`url`(可加 `body`)匹配;以 JSON `save`/`load` 卡带。纯标准库。

## 本次更新 (2026-06-21) — 隔舱与速率限制标头

限制并发、遵守服务器退避。完整参考:[`docs/source/Zh/doc/new_features/v74_features_doc.rst`](../docs/source/Zh/doc/new_features/v74_features_doc.rst)。

- **`Bulkhead` / `next_delay` / `parse_retry_after` / `parse_ratelimit`**(`AC_bulkhead_run`、`AC_retry_after`):`resilience` 恢复、`rate_limit` 调速,但没有任何东西限制*同时*进行的调用(缓慢依赖会耗尽所有 worker),且 HTTP 客户端忽略 `Retry-After`/`RateLimit-*`。本功能补上隔舱(满载时以 `BulkheadFullError` 卸除负载的 bounded-concurrency 许可)以及服务器建议延迟(delta 秒或 HTTP-date)的解析器。非阻塞许可计数 → 确定、测试免线程。纯标准库。

## 本次更新 (2026-06-21) — 流式延迟百分位

load/soak 测试的可合并 p99。完整参考:[`docs/source/Zh/doc/new_features/v73_features_doc.rst`](../docs/source/Zh/doc/new_features/v73_features_doc.rst)。

- **`LatencyDigest` / `exact_percentiles`**(`AC_percentiles`):`stats.percentile` 需要完整已排序列表;本功能补上 HdrHistogram 风格的 digest,具 O(1) `record`、内存有界(有效位数分桶)以及跨分片汇聚的 `merge` —— 这正是从各 worker 结果计算正确汇聚 p99 所需的特性。`exact_percentiles` 涵盖小样本集情况(任意分位)。纯标准库 `math`。

## 本次更新 (2026-06-21) — 服务等级目标(SLO)

SLI、错误预算与燃烧率告警。完整参考:[`docs/source/Zh/doc/new_features/v72_features_doc.rst`](../docs/source/Zh/doc/new_features/v72_features_doc.rst)。

- **`evaluate_slo` / `burn_rate` / `burn_alerts` / `default_burn_rules`**(`AC_evaluate_slo`、`AC_burn_alerts`):框架会发出原始信号却没有 SLO 层。本功能在结果记录(`[{timestamp, ok}]`)上计算 SLI、对目标计算错误预算,以及 Google SRE workbook 的**多窗口多燃烧率**告警(1h 达 14.4×、6h 达 6× 呼叫;3d 达 1× 开单 —— 只有当长短窗口双双超过阈值才触发)。记录为纯数据、时钟可注入、完全确定。纯标准库。

## 本次更新 (2026-06-21) — 混沌实验

注入故障、验证系统仍成立。完整参考:[`docs/source/Zh/doc/new_features/v71_features_doc.rst`](../docs/source/Zh/doc/new_features/v71_features_doc.rst)。

- **`ChaosExperiment` / `run_experiment` / `Probe` / `latency_fault` / `exception_fault`**(`AC_run_chaos`):`resilience` 从失败中*恢复*;这则*制造*失败并检查稳态假设是否仍成立(Chaos Toolkit 生命周期 —— 之前验证、注入故障、之后验证、LIFO 回滚)。探针/故障/回滚皆为 callable;时钟/RNG/sleep 可注入,因此实验在测试中**确定地**执行,无真正失败或睡眠。`AC_run_chaos` 以动作列表 spec 驱动。纯标准库。

## 本次更新 (2026-06-21) — JSON 合约与快照比对

比对、取差异与快照 JSON 内容。完整参考:[`docs/source/Zh/doc/new_features/v70_features_doc.rst`](../docs/source/Zh/doc/new_features/v70_features_doc.rst)。

- **`match_json` / `diff_json` / `normalize_json` / `snapshot_json`**(`AC_match_json`、`AC_diff_json`):`json_schema` 以撰写的 schema 验证、`jsonpath` 提取,但没有任何东西能以宽松规则比对两份内容或逐路径取差异。本功能补上合约/快照比对 —— `partial`(子集)、`match_type`(Pact 风格 `like`)、`ignore` 易变路径 —— 返回 `{path, kind}` 不符(`missing`/`extra`/`changed`),外加 golden-master `snapshot_json`。与 `json_schema` + `json_patch` 互补;纯标准库。

## 本次更新 (2026-06-21) — SLSA 构建来源证明

证明构建产生了什么。完整参考:[`docs/source/Zh/doc/new_features/v69_features_doc.rst`](../docs/source/Zh/doc/new_features/v69_features_doc.rst)。

- **`build_provenance` / `subject_for` / `verify_provenance` / `write_provenance`**(`AC_build_provenance`、`AC_verify_provenance`):框架能签署动作文件并盘点依赖项(SBOM),却无法证明*哪个构建产生了什么*。本功能补上 in-toto v1 Statement,携带覆盖文件 `sha256` 摘要的 SLSA v1 provenance predicate,并附上会重新哈希产物的验证器(篡改 → 不符)。与 `action_signing` + `sbom` 互补;纯标准库 `hashlib`+`json`,完全离线。

## 本次更新 (2026-06-21) — 功能旗标

以目标规则与推出切换行为。完整参考:[`docs/source/Zh/doc/new_features/v68_features_doc.rst`](../docs/source/Zh/doc/new_features/v68_features_doc.rst)。

- **`FlagStore` / `evaluate_flag` / `is_enabled` / `assign_variant`**(`AC_evaluate_flag`、`AC_flag_enabled`):`decision_table` 是一次性 DMN,`ab_locator` 是定位器 A/B —— 两者都不是带黏性 % 推出的产品旗标存储库。本功能补上 OpenFeature 形状引擎:目标规则(`eq`/`in`/`semver_*`…)、加权变体、kill switch,以及一致哈希分桶(`sha256(key.salt.context_key)`)使主体具**黏性**。返回 `{value, variant, reason}`(`TARGETING_MATCH`/`SPLIT`/`DISABLED`/`ERROR`)。纯标准库、确定。

## 本次更新 (2026-06-21) — 文本 Diff、应用与三方合并

应用并合并文本 diff。完整参考:[`docs/source/Zh/doc/new_features/v67_features_doc.rst`](../docs/source/Zh/doc/new_features/v67_features_doc.rst)。

- **`unified_diff` / `apply_unified` / `three_way_merge`**(`AC_unified_diff`、`AC_apply_unified`、`AC_three_way_merge`):`difflib` 会*生成* unified diff,但标准库无法*应用*,也没有三方合并。本功能补上缺少的应用器(走访 `@@` 块、验证 context、不符即抛出)与以行为单位的三方合并(不重叠编辑干净合并;重叠则产生 `<<<<<<<` 冲突标记)。与 `json_patch`(结构化 JSON)互补;纯标准库 `difflib`。

## 本次更新 (2026-06-21) — 日历周期规则(RRULE)

排程「每月第 2 个星期二」。完整参考:[`docs/source/Zh/doc/new_features/v66_features_doc.rst`](../docs/source/Zh/doc/new_features/v66_features_doc.rst)。

- **`parse_rrule` / `occurrences` / `next_occurrence`**(`AC_rrule_occurrences`、`AC_rrule_next`):排程器的 cron 只是 5 字段间隔式 —— 无法表达「每月第 2 个星期二」、「每月最后一个工作日」或「连续 10 次的每个工作日」。本功能补上 RFC 5545(iCalendar)RRULE 解析器 + 发生时刻展开器,支持 `FREQ`/`INTERVAL`/`COUNT`/`UNTIL`/`BYDAY`(含序数如 `2MO`/`-1FR`)/`BYMONTHDAY`/`BYMONTH`/`BYSETPOS`/`WKST`。纯标准库 `datetime`+`calendar`,时钟可注入使 `next_occurrence` 确定。

## 本次更新 (2026-06-21) — 统计与 A/B 显著性

判断差异是否为真。完整参考:[`docs/source/Zh/doc/new_features/v65_features_doc.rst`](../docs/source/Zh/doc/new_features/v65_features_doc.rst)。

- **`describe` / `percentile` / `two_proportion_z_test` / `welch_t_test` / `cohens_d` / `chi_square_2x2`**(`AC_describe_stats`、`AC_ab_significance`):`ab_locator` 以原始成功率排名,`run_history` 存储时长,但没有任何东西计算百分位或显著性。本功能补上分析层 —— 摘要统计 + p50/p90/p95/p99、双比例 z 检验(含置信区间)、Welch t 检验(以不完全 beta 取得精确 t 分布 p 值,免 SciPy)、Cohen's d,以及 2×2 卡方。正态 CDF 以 `math.erf` 精确计算;已对齐教科书数值(含 chi²=z² 恒等式)。纯标准库 `math`+`statistics`。

## 本次更新 (2026-06-21) — 全文搜索(BM25)

依相关性对文档语料排名。完整参考:[`docs/source/Zh/doc/new_features/v64_features_doc.rst`](../docs/source/Zh/doc/new_features/v64_features_doc.rst)。

- **`SearchIndex` / `search_documents` / `tokenize`**(`AC_search_documents`、`ac_search_documents`):`fuzzy` 是成对的,`skill_library` 以字母序匹配子字符串 —— 两者都不会依相关性对语料排名。本功能补上以倒排索引、用 Okapi BM25(`k1=1.5`、`b=0.75`、`IDF = ln(1+(N−df+0.5)/(df+0.5))`)或 TF-IDF 排名的搜索,因此罕见词胜过常见词、词频会饱和、长文档被规范化下调。增量 `add`/`remove`、可选停用词、结果确定。纯标准库 `math`+`collections`+`re` —— 无需数据库。

## 本次更新 (2026-06-21) — JSON Pointer、Patch 与 Merge Patch

定址、取差异并修补 JSON。完整参考:[`docs/source/Zh/doc/new_features/v63_features_doc.rst`](../docs/source/Zh/doc/new_features/v63_features_doc.rst)。

- **`resolve_pointer` / `make_patch` / `apply_patch` / `merge_patch` / `make_merge_patch`**(`AC_resolve_pointer`、`AC_apply_json_patch`、`AC_make_json_patch`、`AC_merge_patch`):`jsonpath` 是只读的,`approval` 比较整份产物 —— 没有任何东西能定址单一位置、计算结构化差异或套用部分更新。本功能补上三个 IETF 原语 —— JSON Pointer(RFC 6901)、JSON Patch(RFC 6902,全六种操作,**原子**套用)、JSON Merge Patch(RFC 7386,`null` 删除)—— 适用于配置漂移检测、部分更新、HTTP PATCH 内容与 golden-master 差异。纯标准库 `json`+`copy`,以 RFC 测试向量验证。

## 本次更新 (2026-06-21) — 客户端速率限制

守在 API 配额之内。完整参考:[`docs/source/Zh/doc/new_features/v62_features_doc.rst`](../docs/source/Zh/doc/new_features/v62_features_doc.rst)。

- **`TokenBucket` / `SlidingWindowLimiter` / `throttle`**(`AC_rate_limit`、`ac_rate_limit`):`RetryPolicy`/`CircuitBreaker` 从失败中复原,但没有任何东西塑形调用的*速率*。本功能补上 token bucket(平滑速率 + 突发)、sliding-window 限制器(Cloudflare 的 O(1) 加权计数)以及前缘 throttle 装饰器。每个限制器都接受可注入的 `clock`(`acquire` 另接受 `sleep`),因此在 CI 完全确定、没有真正延迟。`AC_rate_limit` 以具名 bucket 闸控动作,返回 `{acquired, tokens, wait}`。

## 本次更新 (2026-06-21) — JSON Web Token(JWT)

为你自动化的 API 签发与验证 bearer token。完整参考:[`docs/source/Zh/doc/new_features/v61_features_doc.rst`](../docs/source/Zh/doc/new_features/v61_features_doc.rst)。

- **`encode_jwt` / `decode_jwt` / `ClaimsPolicy`**(`AC_jwt_encode`、`AC_jwt_decode`):框架过去有 HMAC *文件*签名与绑定 ACME 的 RS256 JWS,却没有可签发/验证精简 bearer JWT 的工具。本功能补上纯标准库的 HS256/384/512 编解码器,含完整声明验证(`exp`/`nbf`/`aud`/`iss`、可注入时钟),可直接接上 `http_request` 的 bearer 验证。默认即安全:拒绝 `alg:none`、强制算法允许列表(防混淆),并以 `hmac.compare_digest` 比对签名。`AC_jwt_decode` 返回 `{ok, claims}`,让流程不必抛异常即可分支。

## 本次更新 (2026-06-21) — 许可证策略闸门

标记不被允许的依赖项许可证。完整参考:[`docs/source/Zh/doc/new_features/v60_features_doc.rst`](../docs/source/Zh/doc/new_features/v60_features_doc.rst)。

- **`evaluate_sbom` / `evaluate_license` / `normalize_spdx` / `license_findings_to_sarif`**(`AC_check_licenses`、`ac_check_licenses`):SBOM 记录了每个依赖项的许可证名称却从未*判断*它。本功能把许可证字符串规范化为 SPDX id,以允许列表/拒绝列表(内建 `DEFAULT_COPYLEFT` 集合)评估,理解 SPDX 表达式(`OR` = 择一、`AND` = 全部),再把违规桥接到 SARIF(`denied`→error、`unknown`→warning)。纯标准库、完全离线 —— 与 OSV 漏洞通道并列的许可证合规通道。

## 本次更新 (2026-06-21) — OpenVEX 漏洞分级

抑制不影响你的漏洞。完整参考:[`docs/source/Zh/doc/new_features/v59_features_doc.rst`](../docs/source/Zh/doc/new_features/v59_features_doc.rst)。

- **`vex_statement` / `build_vex` / `apply_vex`**(`AC_apply_vex`、`ac_apply_vex`):OSV 扫描器会让每个已知 CVE 一直出现 —— 没有办法记录「我们查过了,这个不影响我们」。本功能撰写 [OpenVEX](https://openvex.dev) 0.2.0 陈述并套用到扫描器的发现项目:`not_affected`/`fixed` **抑制**一项发现,`affected`/`under_investigation` **标注**它。陈述以漏洞 id *或*别名配对,并可限定产品;`not_affected` 需附理由或冲击说明。纯标准库;可直接接在 `AC_scan_vulns` 之后。

## 本次更新 (2026-06-21) — 依赖项漏洞扫描(OSV)

以 SBOM 比对已知 CVE。完整参考:[`docs/source/Zh/doc/new_features/v58_features_doc.rst`](../docs/source/Zh/doc/new_features/v58_features_doc.rst)。

- **`scan_components` / `match_package` / `is_affected` / `findings_to_sarif`**(`AC_scan_vulns`、`ac_scan_vulns`):`build_sbom` 只会*盘点*依赖项,`to_sarif` 只会*导出*发现项目 —— 从未真正**产生**漏洞发现项目。本功能以 SBOM 的 `(ecosystem, name, version)` 组件比对 [OSV](https://osv.dev) 咨询数据库(扫描 `introduced`/`fixed`/`last_affected` 范围、PEP-503 名称规范化、严重度对应 SARIF 等级),并把结果桥接到既有 SARIF 导出器供 GitHub/Azure DevOps 代码扫描。咨询数据库以**数据注入**(离线、确定性);线上 `osv.dev` 查询为可选的 `fetcher` 接缝。纯标准库 `re`。

## 本次更新 (2026-06-21) — JSON Schema 验证

以真正的 schema 验证嵌套 JSON。完整参考:[`docs/source/Zh/doc/new_features/v57_features_doc.rst`](../docs/source/Zh/doc/new_features/v57_features_doc.rst)。

- **`validate_json` / `is_valid` / `assert_schema`**(`AC_validate_json`、`ac_validate_json`):框架过去只会*产生* JSON Schema,而 `data_quality` 是扁平的逐列检查器 —— 两者都无法验证嵌套的 API 请求/响应内容。本功能补上消费端:一个 JSON Schema(Draft 2020-12 子集)验证器,将**每一个**违规以 `{path, keyword, message}` 报告(例如 `$.age maximum`)。涵盖 `type`(含整数值浮点数的 `integer`)、`enum`/`const`、数字/字符串界限、数组与对象关键字、`allOf`/`anyOf`/`oneOf`/`not`、布尔 schema 与本地 `$ref`。纯标准库 `re`;与 `json_query` 及 `http_request` 辅助函数搭配。

## 本次更新 (2026-06-20) — SARIF 2.1.0 发现项目导出

统一扫描结果供 GitHub 代码扫描。完整参考:[`docs/source/Zh/doc/new_features/v56_features_doc.rst`](../docs/source/Zh/doc/new_features/v56_features_doc.rst)。

- **`to_sarif` / `write_sarif` / `make_finding` / `from_lint_issues` / `from_audit_findings`**(`AC_export_sarif`、`ac_export_sarif`):框架的发现项目产生器(action-lint、密钥扫描、WCAG 审计、guardrail)缺乏共通导出。本功能建立 SARIF 2.1.0 文件(自动规则目录 + 稳定 `partialFingerprints` 跨运行去重),供 GitHub/Azure DevOps 代码扫描以定位到行的警示导入。纯标准库 `json`+`hashlib`;转接器规范化既有 lint/audit 形状。

## 本次更新 (2026-06-20) — 文本 PII 检测与遮蔽

在文本泄漏前遮蔽 PII。完整参考:[`docs/source/Zh/doc/new_features/v55_features_doc.rst`](../docs/source/Zh/doc/new_features/v55_features_doc.rst)。

- **`detect_pii` / `redact_pii_text`**(`AC_detect_pii` / `AC_redact_pii`、`ac_*`):图像遮蔽已存在,但文本(OCR、剪贴板、LLM I/O、日志)无字符串级 PII 处理。本功能在纯文本上检测邮件/电话/SSN/信用卡/IPv4/IBAN 并以 `label`/`mask`/`partial`/`hash` 遮蔽。重叠区段会去重(卡号不会同时是电话);模式无回溯风险。纯标准库 `re`+`hashlib`。

## 本次更新 (2026-06-20) — 自我修复定位器回写

保存修正定位器,使修复不被遗忘。完整参考:[`docs/source/Zh/doc/new_features/v54_features_doc.rst`](../docs/source/Zh/doc/new_features/v54_features_doc.rst)。

- **`RepairStore` / `repair_from_heal`**(`AC_repair_record` / `AC_repair_resolved` / `AC_repair_pending` / `AC_repair_approve`、`ac_*`):运行期自我修复过去会**丢弃**修正后的位置,因此每次都重新修复。本功能记录该次修复的修正定位器(坐标/VLM 描述/方法),在 `confidence >= auto_threshold`(默认 0.9)时**自动套用**或排入可审查建议,`resolved(key)` 返回已学到的修正供重用。封闭「修复→持久修正」循环;纯标准库、可完整测试。

## 本次更新 (2026-06-20) — DMN 式决策表

将分支外部化为可审查的规则表。完整参考:[`docs/source/Zh/doc/new_features/v53_features_doc.rst`](../docs/source/Zh/doc/new_features/v53_features_doc.rst)。

- **`evaluate_table` / `DecisionTable`**(`AC_decision_table`、`ac_decision_table`):以一列列的 `conditions -> outputs` 加命中政策(`UNIQUE`/`FIRST`/`PRIORITY`/`COLLECT`)取代嵌套 `AC_if_var` 链。单元格条件为通配符 / 字面值 / `{op, value}`,使用执行器标准比较子(重用,不重复)。纯标准库、可完整测试;DMN 让业务规则数据驱动的方式。

## 本次更新 (2026-06-20) — Saga / 补偿回滚

后续步骤失败时回滚已完成步骤。完整参考:[`docs/source/Zh/doc/new_features/v52_features_doc.rst`](../docs/source/Zh/doc/new_features/v52_features_doc.rst)。

- **`Saga` / `run_saga`**(`AC_run_saga`、`ac_run_saga`):为每个步骤记录补偿动作;任何失败时以 **LIFO** 顺序对已完成步骤执行补偿 —— 单一区块的 `AC_try` 无法提供的持久性事务原语。前向动作/补偿为可调用对象(或 JSON 动作列表),因此可在无副作用下完整单元测试;补偿为尽力而为(失败的回滚会记录,回滚继续)。返回 `{ok, completed, compensated, failed_step, error}`。

## 本次更新 (2026-06-20) — JSONPath 查询

以通配符、递归、过滤查询 API/DB JSON。完整参考:[`docs/source/Zh/doc/new_features/v51_features_doc.rst`](../docs/source/Zh/doc/new_features/v51_features_doc.rst)。

- **`json_query` / `json_query_one` / `json_extract`**(`AC_json_query` / `AC_json_extract`、`ac_*`):执行器的路径遍历只会以 `.` 切分并索引 —— 本功能在已解析 JSON 上加入 JSONPath 子集(`$`、`.key`、`[n]`/`[-n]`、`*`/`[*]`、`..` 递归下降、`[?(@.k op v)]` 过滤),让含数组的 API/DB 响应易于提取。`json_extract` 以 `{key: path}` 映射提取成扁平 dict。纯标准库 `re`;这是 `AC_http_to_var` 与 DB-row 流程所缺的路径引擎。

## 本次更新 (2026-06-20) — 多通道 Webhook 通知

通知 Teams/Discord/Slack/webhook。完整参考:[`docs/source/Zh/doc/new_features/v50_features_doc.rst`](../docs/source/Zh/doc/new_features/v50_features_doc.rst)。

- **`notify_webhook` / `WebhookChannel`**(`AC_notify_webhook`、`ac_notify_webhook`):`notify` 仅限桌面弹窗、ChatOps 只内建 Slack —— 本功能可发送到 **Slack / Discord / Microsoft Teams / raw** webhook,组出对应传输的载荷(Slack 与 Teams MessageCard 用 `text`,Discord 用 `content`)并通过受出口守卫保护的 HTTP 客户端 POST。`poster` 传输可注入(或 `set_default_poster`),因此发送在无网络下即可单元测试。

## 本次更新 (2026-06-20) — 对外 CloudEvents 发送器

将运行/自动化事件以 CloudEvents 发送。完整参考:[`docs/source/Zh/doc/new_features/v49_features_doc.rst`](../docs/source/Zh/doc/new_features/v49_features_doc.rst)。

- **`to_cloudevent` / `EventEmitter` / `post_cloudevent`**(`AC_emit_event`、`ac_emit_event`):本项目能接收 webhook 却无法**发送**事件 —— 本功能将运行生命周期/断言/失败数据包进 CloudEvents 1.0(CNCF)信封,并可通过受出口守卫保护的 HTTP 客户端 POST 出去(与 Knative、Azure Event Grid、iPaaS、一般 webhook 互通)。`sink`/`poster` 传输可注入,因此发送在无网络下即可单元测试。

## 本次更新 (2026-06-20) — 环境范围的带类型资产存储

依环境的带类型配置 + credential 引用。完整参考:[`docs/source/Zh/doc/new_features/v48_features_doc.rst`](../docs/source/Zh/doc/new_features/v48_features_doc.rst)。

- **`AssetStore` / `active_environment`**(`AC_set_asset` / `AC_get_asset` / `AC_list_assets`、`ac_*`):orchestrator 的「Assets/lockers」支柱 —— 集中管理、依环境(dev/staging/prod)而异且带类型(`text`/`int`/`bool`/`credential`)的配置值。`get` 转成声明类型并退回 default 环境;`credential` 资产持有密钥*引用*,由 `resolve` 通过注入解析器转成真实值(仅限 Python,因此密钥永不进入 `get`/executor 记录)。补足密钥保险库(仅密钥)与 config-sync(整块)的缺口。

## 本次更新 (2026-06-20) — 任务 / 流程挖掘(自动化候选发现)

从录制的动作日志发现该自动化什么。完整参考:[`docs/source/Zh/doc/new_features/v47_features_doc.rst`](../docs/source/Zh/doc/new_features/v47_features_doc.rst)。

- **`mine_action_log` / `find_repeated_sequences` / `directly_follows` / `rank_automation_candidates`**(`AC_mine_actions`、`ac_mine_actions`):挖掘录制的动作日志中频繁、可重复的指令 n-gram,建立 directly-follows 图,并依 `count × length` 为自动化候选排名 —— 这是 AutoControl 一直在录数据却从未分析的 RPA「任务挖掘」支柱。纯标准库;作用于既有动作列表结构;一个经常重现且横跨多步的候选,是「抽成 skill」的强烈信号。

## 本次更新 (2026-06-20) — 卡循环守卫(Agent Loop 进度检测)

捕捉卡在无进展循环的 agent。完整参考:[`docs/source/Zh/doc/new_features/v46_features_doc.rst`](../docs/source/Zh/doc/new_features/v46_features_doc.rst)。

- **`LoopGuard` / `digest_result`**(`AC_loop_guard_observe` / `AC_loop_guard_reset`、`ac_*`):电脑操作最主要的失败模式是 agent 重复一个无效果的动作 —— 而模型看不到自己的循环。`LoopGuard` 观察 `(tool, args, result)` 流并标记 `repeat`(相同调用 N 次)、`ping_pong`(A-B-A-B)与 `no_op`(观察摘要不变),依执行长度由 `ok`→`warn`→`critical` 升级。与步数/时间预算及离线轨迹评估互补;纯标准库、具确定性。

## 本次更新 (2026-06-20) — 坐标空间映射(模型网格 ⇄ 物理像素)

将电脑操作模型的点击转成物理像素。完整参考:[`docs/source/Zh/doc/new_features/v45_features_doc.rst`](../docs/source/Zh/doc/new_features/v45_features_doc.rst)。

- **`CoordinateSpace` / `xga_space` / `normalized_space` / `downscale_png`**(`AC_to_physical` / `AC_to_model`、`ac_*`):电脑操作/VLA 模型以固定网格点击(Anthropic 缩小到 XGA;Gemini 返回 1000×1000 网格),而非物理像素。本功能双向映射(四舍五入 + 夹限),`xga_space` 保持长宽比且不放大,`downscale_png` 将截图缩到模型输入尺寸(Pillow,已是核心)。纯算术映射 —— 无需模型/GPU 即可单元测试。

## 本次更新 (2026-06-20) — 语音指令路由器

以已识别语音免手动触发流程。完整参考:[`docs/source/Zh/doc/new_features/v44_features_doc.rst`](../docs/source/Zh/doc/new_features/v44_features_doc.rst)。

- **`VoiceRouter`**(`AC_voice_register` / `AC_voice_dispatch` / `AC_voice_list` / `AC_voice_clear`、`ac_*`):将语音触发短语映射到 `AC_*` 动作列表;喂入已识别文本即执行最接近的已注册指令(短语匹配重用模糊匹配器,因此「save the file」会触发「save file」)。**语音转文本不在范围内且可注入** —— 路由器接受文本与 `recognizer`/`runner` 可调用对象,因此路由在无音频、无任何语音依赖下完整单元测试(真实 Vosk/麦克风识别器接入 `listen_once`)。

## 本次更新 (2026-06-20) — 区域设置感知的数字、货币与日期解析

解析本地化的数字/货币/日期。完整参考:[`docs/source/Zh/doc/new_features/v43_features_doc.rst`](../docs/source/Zh/doc/new_features/v43_features_doc.rst)。

- **`parse_decimal` / `parse_number` / `format_decimal` / `format_currency` / `format_date`**(`AC_parse_decimal` / `AC_parse_number` / `AC_format_decimal` / `AC_format_currency` / `AC_format_date`、`ac_*`):像 `"1.234,56"`(de_DE)这样的 OCR/UI 文本会通过 **Babel** 的 CLDR 数据正确解析为 `1234.56`,值也能依区域设置格式化回去。`babel` 为可选 `[locale]` extra,采延迟导入;功能测试以 `importorskip` 运行(wiring/facade 一律验证)。

## 本次更新 (2026-06-20) — 感知哈希图像去重

收合近乎相同的屏幕截图。完整参考:[`docs/source/Zh/doc/new_features/v42_features_doc.rst`](../docs/source/Zh/doc/new_features/v42_features_doc.rst)。

- **`average_hash` / `dhash` / `hamming_distance` / `images_similar` / `dedupe_images`**(`AC_image_hash` / `AC_dedupe_images`、`ac_*`):感知哈希将视觉相似的图像映射到接近的指纹,因此录像或步骤报告中的近似重复画面可依汉明距离分群并收合为一个代表。使用 **Pillow**(已是核心 —— 无额外依赖);去重/比较逻辑为纯 Python 且 `hasher` 可注入,因此分群在无任何图像下单元测试,实际 Pillow 路径以 `importorskip` 测试。

## 本次更新 (2026-06-20) — S3 兼容成品存储

将运行成品推送到对象存储。完整参考:[`docs/source/Zh/doc/new_features/v41_features_doc.rst`](../docs/source/Zh/doc/new_features/v41_features_doc.rst)。

- **`S3ArtifactStore`**(`AC_s3_upload` / `AC_s3_download` / `AC_s3_list` / `AC_s3_delete`、`ac_*`):对任何 S3 兼容存储桶(AWS S3、MinIO、R2)上传/下载/列出/删除报告、屏幕截图与录像。`boto3` 为**可选** `[s3]` extra,且 client **可注入**,因此存储体逻辑(含 executor 路径)以假 client 完整单元测试(无 boto3/网络);实际 AWS 路径诚实标注为 CI 无法验证。整个 API 相对于存储体 `prefix`。模块级的默认存储体支撑这些指令。

## 本次更新 (2026-06-20) — 模糊字符串匹配与去重

稳健匹配含噪声的 OCR/UI 文本。完整参考:[`docs/source/Zh/doc/new_features/v40_features_doc.rst`](../docs/source/Zh/doc/new_features/v40_features_doc.rst)。

- **`fuzzy_ratio` / `fuzzy_best_match` / `fuzzy_matches` / `fuzzy_dedupe`**(`AC_fuzzy_ratio` / `AC_fuzzy_best_match` / `AC_fuzzy_dedupe`、`ac_*`):为相似度评分(0..1)、从列表挑最接近的候选,或收合近似重复 —— 让流程可针对「*看起来像* Submit 的按钮」动作,而非精确标签。默认后端为标准库 `difflib`(**无额外依赖**);可选的 `[fuzzy]` extra 加入 `rapidfuzz` 以加速,两者分数皆归一化。支持 `ignore_case` 与 `score_cutoff`。

## 本次更新 (2026-06-19) — 视频步骤叠加报告

将屏幕截图加上字幕制成走查视频。完整参考:[`docs/source/Zh/doc/new_features/v39_features_doc.rst`](../docs/source/Zh/doc/new_features/v39_features_doc.rst)。

- **`write_step_video`**(`AC_write_step_video`、`ac_write_step_video`):将各步骤的屏幕截图转成可分享的视频,每个画面停留数秒并烧入其字幕与通过/失败色彩横幅。组装逻辑(`build_overlay_plan` / `render_overlay_frame`)通过可注入的 `loader`/`drawer`/`writer_factory` 钩子与 OpenCV 分离 —— 可用假物件单元测试、无 `cv2`/`numpy` 依赖;真实路径仅在缺少这些钩子时才延迟导入 `cv2`。为 HTML/JSON 报告的视觉伙伴。

## 本次更新 (2026-06-19) — Agent 可观测性(GenAI OpenTelemetry Spans)

LLM 运行的 OTel GenAI 惯例 spans。完整参考:[`docs/source/Zh/doc/new_features/v38_features_doc.rst`](../docs/source/Zh/doc/new_features/v38_features_doc.rst)。

- **`AgentTrace`**(`AC_trace_record` / `AC_trace_summary` / `AC_trace_export` / `AC_trace_reset`、`ac_*`):记录的 span 其属性遵循 OpenTelemetry **GenAI 语意惯例**(`gen_ai.operation.name`、`gen_ai.system`、`gen_ai.request.model`、`gen_ai.usage.input_tokens`/`output_tokens`、`gen_ai.tool.name`)与 `"{operation} {model}"` span 名称。`to_otel()` 可送入 OTLP exporter;`summary()` 汇整 token 成本与延迟;`operation()` 上下文管理器为实时区块计时并标记错误。纯标准库(无 `opentelemetry` 依赖)、可注入时钟;与轨迹评估互补(在此记录、在那里评分)。

## 本次更新 (2026-06-19) — 合规控制报告(SOC2 / ISO 27001)

将治理证据映射到具名控制项。完整参考:[`docs/source/Zh/doc/new_features/v37_features_doc.rst`](../docs/source/Zh/doc/new_features/v37_features_doc.rst)。

- **`build_compliance_report`**(`AC_compliance_report`、`ac_compliance_report`):框架已内建审计员关注的控制项 —— 出口允许清单、JIT 凭证租约、maker-checker 审批、密钥扫描器、审计记录、CycloneDX SBOM。本功能将扁平的 `evidence` 映射表映射到 SOC2(CC6.1/CC6.3/CC6.8/CC7.3/CC8.1)与 ISO 27001(A.5.23/A.8.16/A.8.30)控制项,每项标记为 `satisfied`/`gap`/`not_assessed`,并输出 JSON 或独立 HTML 表格。治理套件的收尾 —— 为报告辅助,非认证。

## 本次更新 (2026-06-19) — Agent 轨迹评估

依评分标准为 agent 运行评分。完整参考:[`docs/source/Zh/doc/new_features/v36_features_doc.rst`](../docs/source/Zh/doc/new_features/v36_features_doc.rst)。

- **`evaluate_trajectory`**(`AC_evaluate_trajectory`、`ac_evaluate_trajectory`):依声明式评分标准 —— `required_actions`(+`ordered`)、`forbidden_actions`、`max_steps`、`success_contains` —— 为一次记录的轨迹(有序 `{action, args, observation}` 步骤)评分。返回 `{passed, score, steps, checks}`,其中 `score` 为通过的适用检查占比,每个 `check` 精准指出被违反的期望。为 agent 回归测试提供确定性、无依赖的信号;rubric 为纯数据,可存于 JSON action 文件并经 MCP 传递。

## 本次更新 (2026-06-19) — 核准式测试(Golden-Master 基准)

将输出锁定到人工核准的基准。完整参考:[`docs/source/Zh/doc/new_features/v35_features_doc.rst`](../docs/source/Zh/doc/new_features/v35_features_doc.rst)。

- **`verify_artifact` / `approve_artifact`**(`AC_verify_artifact` / `AC_approve_artifact` / `AC_pending_artifacts`、`ac_*`):对*任何*产物(文本、JSON、OCR 输出、屏幕截图字节)进行 golden-master / snapshot 测试。`verify_artifact` 将产出内容与 `<name>.approved.<ext>` 比对;不符或缺少基准会写入 `<name>.received.<ext>` 供审查并失败,`approve_artifact` 则将审查后的 received 文件晋升为基准。以与测试一起提交、受审查把关的基准补强逐像素比对;名称会经过路径穿越检查。

## 本次更新 (2026-06-19) — 网络出口允许清单守卫

钉选自动化可连线的主机。完整参考:[`docs/source/Zh/doc/new_features/v34_features_doc.rst`](../docs/source/Zh/doc/new_features/v34_features_doc.rst)。

- **`EgressPolicy` / `set_egress_policy`**(`AC_egress_allow` / `AC_egress_check` / `AC_egress_reset`、`ac_*`):允许清单(默认拒绝)与/或拒绝清单,使用 `fnmatch` 主机通配符(`*.example.com`),由**每一次** `http_request` 咨询(因此 `AC_http` 与所有以其为基础的功能一次涵盖)。被封锁的主机会在 socket 打开**之前**抛出 `EgressBlocked`。以 allow-all 模式启动 —— 操作者锁定前不改变任何行为。封闭无人值守自动化的数据外泄面。

## 本次更新 (2026-06-19) — 即时凭证租约

密钥的零常驻权限。完整参考:[`docs/source/Zh/doc/new_features/v33_features_doc.rst`](../docs/source/Zh/doc/new_features/v33_features_doc.rst)。

- **`CredentialBroker`**(`AC_lease_secret` / `AC_lease_valid` / `AC_revoke_lease` / `AC_lease_active`、`ac_*`):使用者取得短效*租约*(绑定密钥名称 + 到期时间的 token);真正的值仅在 `redeem` 时、且仅在有效期间,通过可插拔解析器(已解锁的 `SecretManager`、环境变量、vault)取得。密钥值永不进入 executor/MCP 记录 —— executor/MCP/Builder 接口仅管理租约生命周期;`redeem` 是刻意设计的仅限 Python API 逃生门。时钟与解析器皆可注入。

## 本次更新 (2026-06-19) — Maker-Checker 审批闸门

高风险步骤的职责分离。完整参考:[`docs/source/Zh/doc/new_features/v32_features_doc.rst`](../docs/source/Zh/doc/new_features/v32_features_doc.rst)。

- **`ApprovalGate`**(`AC_approval_request` / `AC_approval_approve` / `AC_approval_reject` / `AC_approval_status`、`ac_*`):由 *maker* 提出高风险动作并取得 token;*checker*(必须为**不同**主体)核准或驳回;只有在 `is_approved` 为真后动作才继续。状态为选用的共享 JSON 文件,让派发器与人工审批者可分属不同进程。纯标准库,SOC2 式四眼原则控制。

## 本次更新 (2026-06-19) — Plugin SDK

通过 entry points 注册第三方 `AC_*` 指令。完整参考:[`docs/source/Zh/doc/new_features/v31_features_doc.rst`](../docs/source/Zh/doc/new_features/v31_features_doc.rst)。

- **`discover_plugins` / `load_plugins`**(`AC_list_plugins` / `AC_load_plugins`、`ac_*`):pip 包以 `je_auto_control.commands` entry-point 组声明式注册新执行器指令;AutoControl 于运行期发现并注册(立即可用于 JSON 流程、socket server、调度器、MCP)。坏插件会跳过;为运行期路径加载器的声明式、带命名空间对应物。

## 本次更新 (2026-06-19) — MCP 结构化输出

MCP 2025-06-18 结构化工具输出。完整参考:[`docs/source/Zh/doc/new_features/v30_features_doc.rst`](../docs/source/Zh/doc/new_features/v30_features_doc.rst)。

- **`MCPTool(output_schema=...)`** — 工具可声明 `outputSchema`;其 dict 结果会在 `tools/call` 响应以 `structuredContent` 返回,让客户端/LLM 消费类型化、经 schema 验证的对象而非重新解析文本。`to_descriptor()` 会在 `tools/list` 公告;非 dict 结果与未声明 schema 的工具行为不变。`ac_validate_rows` 为首个采用。

## 本次更新 (2026-06-19) — 缓动拖拽

确定性的缓动拖拽。完整参考:[`docs/source/Zh/doc/new_features/v29_features_doc.rst`](../docs/source/Zh/doc/new_features/v29_features_doc.rst)。

- **`tween_points` / `tween_drag` / `easing_names`**(`AC_tween_drag`、`ac_tween_drag`):沿缓动曲线从 `start` 拖到 `end`(linear / ease_in_out_quad / ease_out_cubic / ease_in_cubic)——确定性、纯数学路径、测试可注入 sink;补足人性化抖动。

## 本次更新 (2026-06-19) — 流程文档(SOP)生成器

把动作列表转成逐步 SOP。完整参考:[`docs/source/Zh/doc/new_features/v28_features_doc.rst`](../docs/source/Zh/doc/new_features/v28_features_doc.rst)。

- **`generate_sop` / `write_sop`**(`AC_generate_sop`、`ac_generate_sop`):把录制/编写的动作列表映射成编号、人类可读步骤 + HTML 文档(UiPath Task-Capture 产出);内容 HTML 转义,未知指令优雅降级。

## 本次更新 (2026-06-19) — 修复分析与机密扫描

两项纯标准库的审计/分析工具。完整参考:[`docs/source/Zh/doc/new_features/v27_features_doc.rst`](../docs/source/Zh/doc/new_features/v27_features_doc.rst)。

- **自我修复分析** — `analyze_heal_log` / `heal_stats`(`AC_heal_stats`、`ac_heal_stats`):把自我修复记录汇总成 heal-rate、策略组合、fallback-rate、平均延迟与最脆弱定位器——在选择器衰退失效前抓出来。
- **机密扫描** — `scan_secrets(data)`(`AC_scan_secrets`、`ac_scan_secrets`):标记 action JSON 中应改用 `${secrets.*}` 的硬编码机密(依键名、值样式或高熵);保险库引用会略过、预览掩码。

## 本次更新 (2026-06-19) — CI 注解与剪贴板历史

两项纯标准库工具。完整参考:[`docs/source/Zh/doc/new_features/v26_features_doc.rst`](../docs/source/Zh/doc/new_features/v26_features_doc.rst)。

- **CI 注解** — `emit_annotations(results)`(`AC_ci_annotations`、`ac_ci_annotations`):把结果 dict 转成 GitHub Actions 工作流命令(`::error file=...,line=...::msg`),让失败在 PR 行内显示,免 reporter action。
- **剪贴板历史** — `ClipboardHistory` / `default_clipboard_history`(`AC_clip_history_capture`/`list`/`search`/`start`/`stop`、`ac_clip_history_*`):有上限、可搜索、最新在前的复制文本环形缓冲,含可选后台轮询器。

## 本次更新 (2026-06-19) — 韧性原语

可重用的 retry 与断路器原语。完整参考:[`docs/source/Zh/doc/new_features/v25_features_doc.rst`](../docs/source/Zh/doc/new_features/v25_features_doc.rst)。

- **RetryPolicy** — `RetryPolicy(...).run(fn)` / `retry_call(fn)`:在配置的异常上以指数退避重试(可注入 sleep)。(既有 `AC_retry` 流程指令已能对动作 body 重试;这是可重用的可调用包装器。)
- **CircuitBreaker** — `CircuitBreaker` / `CircuitOpenError`(`AC_circuit_call`、`ac_circuit_call`):连续失败 N 次后打开、短路至重置超时、再半开——避免重试风暴打垮已故障依赖。可注入 clock;`AC_circuit_call` 让动作列表通过具名断路器执行。

## 本次更新 (2026-06-19) — 计时输入宏

以时间保真度重播输入 + 按住-放开 DSL,走完整五层。完整参考:[`docs/source/Zh/doc/new_features/v24_features_doc.rst`](../docs/source/Zh/doc/new_features/v24_features_doc.rst)。

- **计时时间轴重播** — `replay_timeline(events, speed=...)`(`AC_replay_timeline`、`ac_replay_timeline`):遵守每个 `delta_ms` 间隔、按 `speed` 缩放且可夹限;op = move/click/scroll/press/release/key。
- **输入序列 DSL** — `run_sequence(steps)`(`AC_input_sequence`、`ac_input_sequence`):声明式按住-放开组合键 + `repeat`/`wait`。两者均可注入 sink+sleep 做确定性测试。

## 本次更新 (2026-06-19) — 语义屏幕状态

像素差异的语义对应物,走完整五层。完整参考:[`docs/source/Zh/doc/new_features/v23_features_doc.rst`](../docs/source/Zh/doc/new_features/v23_features_doc.rst)。

- **快照与差异** — `snapshot` / `diff_snapshots` / `snapshot_screen` / `screen_changed`(`AC_screen_snapshot` / `AC_screen_diff` / `AC_screen_changed`、`ac_*`):把 a11y 树规范化为 `{role, name, bbox}`,报告**出现 / 消失 / 移动**并附人类可读摘要——agent 验证某步效果所需的反馈信号(「Save 对话框出现了」)。
- **描述屏幕** — `describe_screen`(`AC_describe_screen`、`ac_describe_screen`):廉价的「我在哪」——各 role 计数 + 交互控件标签。

## 本次更新 (2026-06-19) — Set-of-Marks 叠图

VLM 定位的标准格式,走完整五层。完整参考:[`docs/source/Zh/doc/new_features/v22_features_doc.rst`](../docs/source/Zh/doc/new_features/v22_features_doc.rst)。

- **元素标号** — `mark_elements` / `render_marks` / `resolve_mark`(纯函数 + Pillow):为可交互元素指派 `1..N`(含中心/role/text),在截图上画编号红框,并把选到的编号对应回元素——让 VLM 挑*编号*而非猜像素(直接强化既有 VLM locator)。
- **标号后点击循环** — `mark_screen(render_path=...)` / `mark_click(n)`(`AC_mark_screen` / `AC_mark_click`、`ac_*`):为实时 a11y 树标号(+可选叠图截图),把 marks+图像喂给模型,再点击第 `n` 号。

## 本次更新 (2026-06-19) — 检查点与续跑

长流程的耐久执行 + `py.typed` 标记,走完整五层。完整参考:[`docs/source/Zh/doc/new_features/v21_features_doc.rst`](../docs/source/Zh/doc/new_features/v21_features_doc.rst)。

- **流程检查点与续跑** — `run_resumable(actions, run_id=..., store=...)` / `CheckpointStore`(`AC_run_resumable` / `AC_checkpoint_status` / `AC_checkpoint_clear`、`ac_*`):每步后持久化 step-index + 变量;以相同 `run_id` 再执行时快进略过已完成步骤并还原变量——在第 400 步崩溃的流程会从 400 续跑,而非从 0。可抽换(默认 SQLite),完成后清除。
- **`py.typed` 标记** — 附带 PEP 561 标记,让 Mypy/Pyright/Pylance 在下游代码采用 AutoControl 的内嵌类型注解(此前类型化 API 对类型检查器是隐形的)。

## 本次更新 (2026-06-19) — i18n / l10n 测试

三项可互相搭配的纯标准库国际化/本地化测试辅助工具,走完整五层。完整参考:[`docs/source/Zh/doc/new_features/v20_features_doc.rst`](../docs/source/Zh/doc/new_features/v20_features_doc.rst)。

- **伪本地化** — `pseudo_localize` / `pseudo_localize_catalog`(`AC_pseudo_localize`、`ac_pseudo_localize`):为 UI 字符串加重音与填充(保留占位符、以 `⟦…⟧` 包裹),在真正翻译前揪出硬编码文本并对版面施压。
- **文本溢出检测** — `check_overflow(elements)`(`AC_check_overflow`、`ac_check_overflow`):标记估计宽度超过控件边界的文本(本地化头号 bug),由 AutoControl 既有读取的 a11y 边界计算。
- **目录完整性** — `check_catalog(base, target)`(`AC_check_catalog`、`ac_check_catalog`):比对翻译目录的缺失/多余/空白键与占位符不一致——防止空白 UI 的 CI 闸。

## 本次更新 (2026-06-19) — 数据质量

三项纯标准库的数据质量辅助工具(介于 `load_rows`/OCR 与下游输入之间的闸),走完整五层。完整参考:[`docs/source/Zh/doc/new_features/v19_features_doc.rst`](../docs/source/Zh/doc/new_features/v19_features_doc.rst)。

- **数据行 schema 验证** — `validate_rows(rows, schema)`(`AC_validate_rows`、`ac_validate_rows`):声明式逐字段规则(type/required/regex/min/max/min_len/max_len/allowed/unique);返回 `{ok, valid, invalid, errors}`,在坏掉的抓取/OCR 数据污染 ERP/表单前拦下。
- **字段提取** — `extract_fields(text, fields, patterns)`(`AC_extract_fields`、`ac_extract_fields`):具名 regex 预设(email/url/ipv4/phone/date_iso/amount/hashtag)+自定义 patterns,作用于自由文本 / OCR 文本块。
- **数据行掩码** — `mask_rows(rows, rules)`(`AC_mask_rows`、`ac_mask_rows`):导出前掩码字段——`redact` / `hash`(SHA-256)/ `partial`(保留末 4 字);补足仅针对截图的脱敏。

## 本次更新 (2026-06-19) — SBOM 与测试分片

来自安全与规模研究角度的两项纯标准库运维工具,走完整五层。完整参考:[`docs/source/Zh/doc/new_features/v18_features_doc.rst`](../docs/source/Zh/doc/new_features/v18_features_doc.rst)。

- **CycloneDX SBOM** — `build_sbom` / `write_sbom`(`AC_generate_sbom`、`ac_generate_sbom`):为供应链合规(欧盟 CRA / EO 14028)输出 CycloneDX 1.6 依赖 SBOM(name/version/purl/许可证);`root` 限定某包的闭包,`extra_components` 可纳入 action 文件。无第三方依赖。
- **时长感知套件分片** — `shard_flows` / `merge_results`(`AC_shard_suite` / `AC_merge_results`):依每个流程历史时长把流程装箱成 N 片(让最慢的 worker 而非测试数量决定总时长),再把各分片报告合并为一份汇总。

## 本次更新 (2026-06-19) — 反应式观察器

非阻塞的屏幕观察器(SikuliX `observe` 模型),走完整五层(facade、`AC_*`、MCP、Script Builder)。完整参考:[`docs/source/Zh/doc/new_features/v17_features_doc.rst`](../docs/source/Zh/doc/new_features/v17_features_doc.rst)。

- **`ScreenObserver`**(`AC_observe_add` / `AC_observe_remove` / `AC_observe_list` / `AC_observe_poll` / `AC_observe_start` / `AC_observe_stop`、`ac_observe_*`):注册监看,在图像/文本/像素的 **appear** / **vanish** / **change** 时触发回调或执行 action list——在主流程继续的同时对对话框/进度/状态做出反应。
- **为可测试而设计**——检测是可注入的 `predicate`;转换逻辑用 `poll_once()` 以合成值做单元测试。内建 `image_predicate` / `text_predicate` / `pixel_predicate` 包装既有的 locate/OCR/pixel 辅助函数。

## 本次更新 (2026-06-19) — WCAG 2.2 审计

无障碍审计新增 WCAG 2.2 / EN 301 549 成功准则层,走完整五层(facade、`AC_*`、MCP、Script Builder)。完整参考:[`docs/source/Zh/doc/new_features/v16_features_doc.rst`](../docs/source/Zh/doc/new_features/v16_features_doc.rst)。

- **WCAG 标注合规审计** — `wcag_audit(level="AA")`(`AC_wcag_audit`、`ac_wcag_audit`):为每个缺陷标注 WCAG 成功准则编号/等级/影响(4.1.2、1.4.3、1.4.10),返回含 `by_criterion`/`by_impact` 计数的合规报告,按 A/AA/AAA 过滤——可对应 EN 301 549 作为 EAA 合规证据。
- **目标尺寸(SC 2.5.8)** — `audit_target_size(elements, min_px=24)`:WCAG 2.2 新规则,由元素 bounds 标记小于 24×24 px 的交互目标;`tag_issue` 可为任何既有审计问题加上 SC 标注。

## 本次更新 (2026-06-19) — 记忆与确定性

由 agent/QA 研究轮找出的两项纯标准库工具,走完整五层(facade、`AC_*`、MCP、Script Builder)。完整参考:[`docs/source/Zh/doc/new_features/v15_features_doc.rst`](../docs/source/Zh/doc/new_features/v15_features_doc.rst)。

- **Agent 情节记忆** — `AgentMemory`(`AC_memory_remember` / `AC_memory_recall` / `AC_memory_recent` / `AC_memory_forget` / `AC_memory_stats`、`ac_memory_*`):以 SQLite 存储 `(目标 → 轨迹 → 结果)` 情节,依关键字召回过往经验注入规划器上下文——跨执行学习,免向量依赖。
- **确定性执行** — `DeterministicRun` / `seed_everything`(`AC_seed_everything`、`ac_seed_everything`):在 `with` 块内固定 RNG 种子并冻结 `time.time`(记录选择以便重现),消除时间/随机造成的不稳定;`time.monotonic` 保持不变,超时仍正常。

## 本次更新 (2026-06-19) — Office 读写

Excel/Word/PowerPoint 的 headless 读写,走完整五层(facade、`AC_*`、MCP、Script Builder)。可选 extra:`pip install je_auto_control[office]`。完整参考:[`docs/source/Zh/doc/new_features/v14_features_doc.rst`](../docs/source/Zh/doc/new_features/v14_features_doc.rst)。

- **Excel** — `read_workbook` / `write_workbook`(`AC_read_workbook` / `AC_write_workbook`、`ac_read_workbook` / `ac_write_workbook`):把 `.xlsx` 工作表读成数据行字典(第一行为键)并写回,不需 GUI。
- **Word** — `read_document` / `write_document`(`AC_read_document` / `AC_write_document`):读写 `.docx` 段落。
- **PowerPoint** — `read_presentation` / `write_presentation`(`AC_read_presentation` / `AC_write_presentation`):读取每张幻灯片文本;以 `{title, body:[...]}` 写入幻灯片。

背后函式库(`openpyxl`/`python-docx`/`python-pptx`)为可选——缺少时每个调用会抛出清楚错误,且 `import je_auto_control` 不会载入它们。

## 本次更新 (2026-06-19) — Agent 工具组

三项供 LLM / agent 驱动自动化使用的纯标准库工具,走完整五层(facade、`AC_*`、MCP、Script Builder)。完整参考:[`docs/source/Zh/doc/new_features/v13_features_doc.rst`](../docs/source/Zh/doc/new_features/v13_features_doc.rst)。

- **技能 / playbook 库** — `SkillLibrary`(`AC_skill_save` / `AC_skill_run` / `AC_skill_list` / `AC_skill_remove` / `AC_skill_search`、`ac_skill_*`):把具名、可重用的动作序列存到磁盘,依名称/说明/标签搜索,并跨执行重播——内存内宏的持久化对应物。
- **Prompt-injection 防御闸** — `assess_text` / `scan_text` / `redact_text`(`AC_guard_text`、`ac_guard_text`):在把不可信的屏幕/OCR 文本喂给 LLM 前,扫描注入样式(指令覆写、系统提示外泄、jailbreak/聊天模板标记…);返回 `{suspicious, score, findings, redacted}`。
- **A2A agent card** — `build_agent_card` / `write_agent_card`(`AC_agent_card`、`ac_agent_card`):发布 A2A agent card,让其他 agent 把 AutoControl 当成 GUI 自动化伙伴发现并调用。

## 本次更新 (2026-06-19) — 编写与调试

两项纯标准库的编写期工具,走完整五层(facade、`AC_*`、MCP、Script Builder)。完整参考:[`docs/source/Zh/doc/new_features/v12_features_doc.rst`](../docs/source/Zh/doc/new_features/v12_features_doc.rst)。

- **元素库** — `ElementRepository`(`AC_element_save` / `AC_element_find` / `AC_element_click` / `AC_element_remove` / `AC_element_list`、`ac_element_*`):把原生 UI 定位器以友好名称存起来(object repository)重用——用 `repo.click("login.submit")` 取代到处重复 name/role;UI 变动只需改一处。
- **步进调试器 / 追踪器** — `FlowDebugger`(断点、`step`/`continue_`/`run_to_end`、实时 `variables()`)与 `trace_actions`(`AC_debug_trace`、`ac_debug_trace`):把动作列表一次跑一个指令、变量跨步保留,或获取每步 `{index, command, result}` 追踪(用 `dry_run` 只规划不执行)。

## 本次更新 (2026-06-19) — 测试与工具三件套

三项纯标准库的生产力工具,走完整五层(facade、`AC_*`、MCP、Script Builder)。完整参考:[`docs/source/Zh/doc/new_features/v11_features_doc.rst`](../docs/source/Zh/doc/new_features/v11_features_doc.rst)。

- **合成测试数据** — `generate_rows(schema, count, seed=...)` / `write_dataset`(`AC_generate_data`、`ac_generate_data`):生成可重现的假数据行(name/email/phone/int/choice/date…),驱动数据驱动执行而不需真实 PII;无需 Faker。
- **MCP registry 清单** — `write_server_manifest("server.json", include_tools=True)`(`AC_mcp_manifest`、`ac_mcp_manifest`):生成符合 registry 规范的 `server.json`,让 MCP agent/IDE 能发现此服务器。
- **风险导向测试选择** — `rank_flows` / `select_flows`(`AC_rank_tests` / `AC_select_tests`):依最近失败、不稳定、陈旧与从未跑过,从 run history 排序流程;先跑最高风险或只跑前 k 个。

## 本次更新 (2026-06-19) — 事务式工作队列

把 AutoControl 从「跑脚本」升级成「跑机器人」。以 SQLite 为底的工作队列实作生产级 RPA dispatcher/performer:入列项目、一次处理一项、具每项状态/去重/重试,使上千项执行能**崩溃后续跑**且可并行化。纯标准库、走完整五层。完整参考:[`docs/source/Eng/doc/new_features/v10_features_doc.rst`](../docs/source/Eng/doc/new_features/v10_features_doc.rst)。

- **Dispatcher/performer** — `WorkQueue.add()` 入列(依 reference 去重);`get_next()` 原子认领最旧项;`complete()` / `fail()` 记录结果。`AC_queue_add` / `AC_queue_next` / `AC_queue_complete` / `AC_queue_fail` / `AC_queue_stats`。
- **失败语义** — application 错误重试至 `max_retries`;**business** 错误(`BusinessError` / `kind="business"`)永不重试。`stats()` 给各状态计数供仪表板。

## 本次更新 (2026-06-19) — 无人值守可靠性

三个无人值守/登录自动化的社区痛点修复,均 headless 且走完整五层。完整参考:[`docs/source/Eng/doc/new_features/v9_features_doc.rst`](../docs/source/Eng/doc/new_features/v9_features_doc.rst)。

- **2FA 的 OTP / TOTP** — `generate_totp` / `verify_totp`(`AC_otp_to_var`、`ac_generate_otp`):从 base32 secret 生成当下 6 位码,填进登录表单(重用远程桌面 TOTP 引擎)。
- **原生文件对话框** — `handle_file_dialog`(`AC_handle_file_dialog`):等 OS 打开/保存/文件夹对话框、输入路径、确认,一次完成,driver 可注入。
- **锁定会话守卫** — `ensure_interactive_session` / `is_session_locked`(`AC_assert_session_active`):工作站锁定/断开时清楚失败,而非发出幽灵点击。

## 本次更新 (2026-06-19) — 弹窗看门狗

无人值守自动化失败的第一大主因,是脚本没写到的意外对话框(UAC、"会话过期"、Windows Update、modal)。弹窗看门狗以并行守卫线程监看注册 pattern,独立于主流程把它们关掉。由社区痛点研究指出为无人值守头号失败主因;走完整五层(facade、`AC_*`、MCP、Script Builder),完全 headless。完整参考:[`docs/source/Eng/doc/new_features/v8_features_doc.rst`](../docs/source/Eng/doc/new_features/v8_features_doc.rst)。

- **自动关闭弹窗** — `default_popup_watchdog.add_window_rule(title, action="close")` 后 `.start()`(`AC_watchdog_add` / `AC_watchdog_start` / `AC_watchdog_stop` / `AC_watchdog_list`):窗口出现时关闭它或按键(`enter`/`esc`)。
- **自定义规则** — `PopupWatchdog` / `WatchdogRule` 把任意检测器(图/a11y/文本)配对关闭器;坏规则只记录并跳过,绝不让守卫循环停摆。

## 本次更新 (2026-06-19) — 原生 UI 控制

对象级桌面自动化:通过 OS 无障碍 API(以 name / role / app / **AutomationId** 定位)读取与操作原生控件,而非点像素或 OCR——对原生 app 可靠得多。无障碍层先前只能 list/find/click,现在还能操作。走完整五层(facade、`AC_*`、MCP、Script Builder),提供 Windows UIAutomation 后端;不支持的后端会抛清楚错误。完整参考:[`docs/source/Eng/doc/new_features/v7_features_doc.rst`](../docs/source/Eng/doc/new_features/v7_features_doc.rst)。

- **读取 / 设置值** — `control_get_value` / `control_set_value`(`AC_control_get_value` / `AC_control_set_value`):读 textbox/combo 值(不用 OCR),一次设置值(不必逐键输入)。
- **调用 / 切换** — `control_invoke` / `control_toggle`(`AC_control_invoke` / `AC_control_toggle`):通过控件模式按按钮或切换复选框。
- **读取表格/列表** — `read_control_table`(`AC_read_table`):把 grid/list/table 控件抓成逐行单元格字符串——不用 OCR 的桌面数据提取。
- 以 `name` / `role` / `app_name` / `automation_id`(Windows 稳定标识符)定位,版面/本地化改变也不坏。

## 本次更新 (2026-06-19)

两个早已存在、却没接上其余各层的 headless 核心,现在成为一级功能。两者都新增 facade re-export、`AC_*` 执行器指令、MCP 工具与 Script Builder 项目,并有 headless 测试。完整参考:
[`docs/source/Eng/doc/new_features/v6_features_doc.rst`](../docs/source/Eng/doc/new_features/v6_features_doc.rst)。

- **视觉回归(黄金图像)** — `take_golden` / `compare_to_golden`(`AC_take_golden` / `AC_assert_visual`):捕获基准截图,画面偏离超过像素容差时判失败,并输出高亮差异图与遮罩区域。`AC_assert_visual` 首跑会自动建立基准。纯 PIL。
- **有限状态机** — `run_state_machine`(`AC_run_state_machine`):把脚本当成声明式 `{initial, states}` spec 驱动,`on_enter` 动作经执行器执行,transition 依 `after` / `if_var_eq` / predicate 触发,并以 `max_steps` / `global_timeout_s` 限制。

## 本次更新 (2026-06-18)

八项 headless 能力,补齐脚本化、集成与 CI 场景:真正的命令行界面、把录制转成代码,以及一级的 HTTP / SQL / Email / PDF / 等待步骤。每项都附带 headless API、`AC_*` 执行器指令、MCP 工具与可视化脚本构建器项目,并有 headless 测试(网络 / SMTP / PDF 后端均注入,不接触外部系统)。完整参考页:
[`docs/source/Eng/doc/new_features/v5_features_doc.rst`](../docs/source/Eng/doc/new_features/v5_features_doc.rst)。

**命令行界面**
- **`je_auto_control` console script** — 在 shell／CI 运行与检查动作文件:`run`(含 `--var`、`--dry-run`)、`validate`(别名 `lint`)、`list-commands`、`fmt`、`record`、`codegen`、`version`。

**代码生成**
- **录制 → 代码** — `generate_code` / `generate_code_file`(`AC_generate_code`、`je_auto_control codegen`):把录制或动作文件转成 pytest／独立 Python／Robot 脚本。默认 `calls` 风格生成可读的 `ac.<fn>(...)`,流程控制退回 `ac.execute_action([...])`。

**集成**
- **HTTP / API** — `http_request`(`AC_http_request`):method、headers、JSON／原始 body、basic／bearer 认证、明确超时;非 2xx 返回而非抛异常。`AC_http_to_var` 现共用此客户端,可发送 body。
- **SQL** — `query_sqlite`(`AC_sql_to_var` / `AC_assert_db`):只读、参数绑定的 SQLite 查询,存入变量或做标量断言。
- **Email(SMTP)** — `send_email`(`AC_send_email`):标准库 SMTP,默认 TLS(STARTTLS／SSL、已验证证书),支持附件与多收件人。
- **PDF** — `extract_pdf_text` / `pdf_metadata` / `assert_pdf_text`(`AC_pdf_to_var` / `AC_assert_pdf_text`):文本提取与内容断言,后端为可选 `pypdf`(`pip install je_auto_control[pdf]`)。

**智能等待**
- **等待文件** — `wait_until_file`(`AC_wait_for_file`):等到文件存在且大小停止增长(下载写完)。
- **等待 TCP 端口** — `wait_until_port`(`AC_wait_for_port`):等到 `host:port` 可连接(与 `launch_process` 互补)。
- **等待进程** — `wait_until_process`(`AC_wait_for_process`):等到进程出现或退出(与 `launch_process` / `kill_process` 互补;需 psutil)。

**安全性** — HTTP／SMTP 强制 http/https 或已验证 TLS 与明确超时;SQL 只读且参数绑定;文件路径 I/O 前以 `realpath` 解析。

## 本次更新 (2026-06-17)

新增 30+ 个自动化原语，涵盖输入拟真、视觉、流程控制、触发器、窗口管理与文件安全，
另加“可还原删除（回收站）”与“编辑器 Undo”。每个都附带 headless API、`AC_*` 执行器
指令，以及可视化脚本构建器项；视觉与窗口功能的 geometry / IO 操作皆可注入，逻辑完全
单元测试。完整参考页：
[`docs/source/Eng/doc/new_features/v4_features_doc.rst`](../docs/source/Eng/doc/new_features/v4_features_doc.rst)。

**拟人化输入**
- **拟人化鼠标移动** — `move_mouse_humanized`：eased bezier 曲线 + overshoot + jitter，seed 可重现（`AC_human_move`）。
- **拟人化打字** — `type_text_humanized`：每字随机微延迟 + 偶尔停顿，seed 可重现（`AC_human_type`）。

**视觉**
- **VLM 自然语言断言** — `assert_by_description`：用 VLM 判断画面是否符合描述（`AC_assert_vlm`）。
- **滚动找元素** — `scroll_until_visible`：往某方向滚动直到图／文字出现（`AC_scroll_to_find`）。
- **区域颜色统计** — `region_color_stats`：平均色 + 主色 + 占比（`AC_region_color_stats`）。
- **读 QR code** — `read_qr_codes`：OpenCV QRCodeDetector 从屏幕区域解 QR（`AC_read_qr`）。

**流程控制与变量**
- **可重用宏** — `AC_define_macro` / `AC_call_macro`：具名、带参数的动作子程序，`${arg}` 绑定。
- **同进程并行** — `AC_parallel`：多分支并行，各自独立 executor，变量不互相 race。
- **性能预算断言** — `assert_duration` / `AC_assert_duration`：超过毫秒预算就判失败。
- **读进变量** — `AC_ocr_to_var`、`AC_shell_to_var`、`AC_read_file_to_var`、`AC_http_to_var`（body 或 dotted JSON path）、`AC_now_to_var`（strftime）、`AC_random_to_var`（seeded）。
- **变量转换** — `AC_transform_var`：upper／lower／strip／title／replace／regex 取出／slice。
- **断言变量** — `assert_variable` / `AC_assert_var`：eq／ne／lt／gt／contains／regex。

**触发器与智能等待**
- **复合触发器** — `AllOfTrigger` / `AnyOfTrigger` / `SequenceTrigger`：布尔 AND／OR／顺序组合任何现有触发器。
- **Cron 触发器** — `CronTrigger`：五字段 cron 排程，每分钟最多一次，可与布尔触发器组合。
- **更多智能等待** — `wait_until_clipboard_changes`（`AC_wait_clipboard_change`）、`wait_until_window_closed`（`AC_wait_window_closed`）。

**窗口管理**
- **单一窗口截图** — `capture_window`：依标题截出该窗口（`AC_capture_window`）。
- **布局存／还原** — `save_window_layout` / `restore_window_layout`：快照所有窗口位置 → JSON → 一键还原。
- **贴齐／分割** — `snap_window`：左／右半、四角、最大化（`AC_snap_window`）。

**文件安全**
- **动作文件签名** — `sign_action_file` / `verify_action_file`（HMAC-SHA256）；`execute_files` 可在 `JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` 下强制验签。
- **动作文件加密** — `encrypt_action_file` / `decrypt_action_file`（Fernet）。
- **可还原删除** — `move_to_trash`：送进操作系统回收站（`AC_move_to_trash`）。

**报告与通知**
- **截图标注** — `annotate_screenshot`：画带标签方框／高亮／箭头／文字（`AC_annotate_screenshot`）。
- **桌面通知** — `notify`：跨平台 toast，injection-safe（`AC_notify`）。

**GUI**
- **录制编辑器 Undo** — 每个编辑都快照；**Ctrl+Z** 与 Undo 按钮还原。
- **触发器页** — “Combine selected”把选中的触发器组成复合；新增 **Cron** 类型。
- **断言页** — 新增 **VLM** 断言类型。
- 所有新 `AC_*` 指令都在可视化 **脚本构建器** 可用。

**修复** — 修了 PySide6 6.11.1 上 USB 授权弹窗的 `Q_ARG(object)` crash、8 个 stale／损坏的测试、2 个丢失异常链，并把 13 个函数拉回 CC≤10。

## 本次更新 (2026-06)

新增 9 个功能，把自动化原语升级成一套完整的 **QA / 测试框架**：验证画面状态、
用数据驱动脚本、检测并隔离不稳定测试、执行计分套件、输出 CI 原生报告、
审计无障碍 / i18n、跨设备矩阵并行执行，以及对音频 / 视频做断言。
每个功能都遵循框架既有模式：headless Python API、`AC_*` executor 命令、
`ac_*` MCP 工具，以及 Qt GUI 选项卡。完整参考页面：
[`docs/source/Zh/doc/new_features/v3_features_doc.rst`](../docs/source/Zh/doc/new_features/v3_features_doc.rst)。

**断言**
- **断言 DSL** — 验证画面状态而不只是操作：`assert_text`（OCR，`regex` + `present=False` 断言不存在）、`assert_image`、`assert_pixel`、`assert_window`、`assert_clipboard`（`equals` / `contains` / `regex`，`present=False` 可确认机密已清除）、`assert_process`（指定名称的进程是否运行中，通过 psutil）。返回 `AssertionResult`，不符时抛出 `AutoControlAssertionException`，可选失败截图（`AC_assert_text / _image / _pixel / _window / _clipboard / _process`）。
- **画面外断言** — `assert_file`（文件存在 / 子串 / SHA-256 / 最小大小，验证下载或导出结果）与 `assert_http`（http/https 端点返回状态码 + 可选正文，一律带显式 timeout）。两者把 DSL 延伸到画面之外，并能接到下方的组合器（`AC_assert_file / AC_assert_http`）。
- **断言组合器** — `assert_all([...specs])` 以*软断言*方式跑完整批（逐一检查、收齐所有失败才抛出）并返回 `GroupAssertionResult`；`assert_any([...specs])` 是 OR 互补（任一通过即通过、短路 — 例如登录成功对话框*或*重定向其一出现即可）；`assert_eventually(spec, timeout, interval)` 重试单个声明式 spec 直到通过或超时（例如轮询健康检查端点直到返回 200，或等待下载文件出现）。均以 spec 驱动（`{"kind": "text", "text": "Saved"}`、`{"kind": "http", "url": "..."}`），在 Python、JSON、MCP 中行为一致,涵盖全部断言类型 — text/image/pixel/window/clipboard/process/file/http（`AC_assert_all / AC_assert_any / AC_assert_eventually`）。
- **媒体断言** — `assert_audio_activity`（录音 + RMS 阈值判断有声 / 静音）与 `assert_video_changes`（视频区段相邻帧平均差异判断动态 / 静止）；纯数值核心，`sounddevice` / OpenCV 延迟加载（`AC_assert_audio / AC_assert_video_changes`）。

**数据驱动执行**
- **数据源** — `load_rows` 支持 CSV / JSON / SQLite / Excel / 内联；`AC_for_each_row` 块命令每行执行一次 body，字段以 `${row.column}` 取用。SQLite 仅允许单句只读 `SELECT`/`WITH`，路径经 `realpath` 校验。`${var}` 插值现在支持点号路径（dict 键 / list 索引）并保留类型（`AC_load_data`）。

**不稳定检测与隔离**
- **不稳定报告** — 从执行历史以通过↔失败翻转率给间歇性失败评分，按 script / source 分组（`AC_flaky_report`）。
- **隔离区** — 套件执行器会遵守的持久化（0600）跳过清单；`auto_quarantine_from_flakiness` 按翻转率阈值自动填入（`AC_quarantine_add / _remove / _list / _clear / _auto`）。

**套件执行器 + CI 报告**
- **QA 套件编排** — `run_suite` 把 action list 变成具 setup / teardown、标签与数据驱动展开的计分用例；断言失败 → failed、其他异常 → error、被隔离 → skipped（`AC_run_suite`）。
- **JUnit / Allure 报告** — `write_junit_xml` + `write_allure_results`（或 `AC_run_suite` 的 `junit_path` / `allure_dir`），输出 Jenkins / GitHub Actions / GitLab CI / Allure 原生解析的报告。

**审计、矩阵、媒体**
- **无障碍 / i18n 审计** — 反向利用 a11y 树 + OCR，找出缺失的可访问名称、WCAG 对比度不足与省略号截断字符串（`AC_audit_accessibility / AC_audit_contrast`）。
- **移动设备矩阵** — 将单一 action list 并行分发到多台 Android / iOS 设备，每台独立 executor，通过 `${device.*}` 锁定当前设备；逐设备通过 / 失败，失败相互隔离（`AC_run_device_matrix`）。

## 本次更新 (2026-05)

新增 27 个功能，覆盖更聪明的定位器、更深的 IDE / 运维工具、
四个新平台后端（Wayland、Wayland-libei、Android widget tree、iOS）、
截屏 PII 脱敏，以及通用 plan-execute-verify agent 循环。
每个功能都遵循框架既有模式：headless Python API、`AC_*` executor 命令、
`ac_*` MCP 工具，以及（适用时）Qt GUI 选项卡。完整参考页面：
[`docs/source/Zh/doc/new_features/v2_features_doc.rst`](../docs/source/Zh/doc/new_features/v2_features_doc.rst)。

**定位器与选择器智能化**
- **自愈定位器** — `image_template → VLM` 后备并写入 JSON-lines 审计记录（`AC_self_heal_locate / _click`）。
- **锚点定位器** — 按空间关系（`above` / `below` / `left_of` / `right_of` / `near`）找到目标；锚点与目标可使用不同 backend（image / OCR / VLM / a11y）。
- **结构化 OCR** — 将原始 OCR match 聚合为 rows、tables、`label:value` 表单字段（`AC_ocr_read_structure`）。
- **智能等待** — `wait_until_screen_stable`、`wait_until_pixel_changes`、`wait_until_region_idle`：用 frame-diff 取代 `time.sleep`。
- **A/B 定位器框架** — 并行跑 N 个策略，依持久化的历史成绩推荐最佳。

**运维与可观测性**
- **LLM 成本遥测** — 每次调用的 token / USD 记录，按天 / 模型 / 提供方汇总（`record_llm_call`、`summarise_llm_costs`）。
- **追踪回放 UI** — 在现有 time-travel 录像上拖动时间轴并逐步显示动作。
- **失败 → 工单自动化** — 调度器／触发器／REST 任务失败时自动分发 Jira / Linear / GitHub Issues。
- **容器化 CI 模板** — GitHub Actions + GitLab CI workflow：构建镜像、跑 headless pytest（Xvfb 容器内）、smoke-test REST entrypoint；另含 XFCE+x11vnc Dockerfile 变体。
- **跨主机 DAG 编排** — 跨 local + admin-console 已注册主机并行执行，失败时下游 cascade 为 `skipped`（`run_dag`、`AC_run_dag`）。
- **多 viewer 名单** — 为远程桌面提供控制者 / 观察者角色，纯 Python `PresenceRegistry` 独立于 aiortc。

**代理与集成**
- **Computer-use 高阶 API** — `run_computer_use(goal, ...)` 封装 `ComputerUseAgentBackend` + `AgentLoop`；自动检测屏幕大小；以 `max_steps` / `wall_seconds` 为预算。
- **通用 agent 循环 JSON / MCP 接入** — `AC_run_agent` / `ac_run_agent` 把闭环 `AgentLoop`（规划 → 执行 → 验证 → 重试）开放给 JSON action 和 MCP 客户端，支持 Anthropic / OpenAI 两种 backend；既有的 Anthropic 原生 Computer-Use 路径仍通过 `AC_computer_use` 提供。
- **WebRunner 便利命令** — 在既有 `je_web_runner` 桥接之上的 `web_open` / `web_quit` / `web_screenshot` / `web_current_url`；同步以 `AC_web_*`、`ac_web_*` 暴露。
- **Chat-ops 机器人** — 传输层中立的 `CommandRouter` + Slack polling adapter。内置命令：`/help`、`/scripts`、`/run`、`/screenshot`、`/status`。RBAC 通过 `required_role`。

**隐私与安全**
- **截屏 PII 脱敏** — `RedactionEngine` 内置检测：email / 信用卡 / SSN / 电话（regex 比对调用方提供的 OCR token）以及 accessibility tree 标记的 secure-text 字段；可指定强制模糊区域。默认策略通过环境变量 `JE_AUTOCONTROL_REDACTION=off|moderate|strict` 控制。执行器命令 `AC_redact_screenshot` 与 MCP `ac_redact_screenshot` 都已接入。

**平台覆盖**
- **Wayland CLI 后端** — `wtype` / `ydotool` / `grim`，按 `XDG_SESSION_TYPE` 自动检测，CLI 工具未装时回退到 X11 (XWayland)；可用 `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11|wayland|auto` 覆盖。
- **Wayland libei 原生后端** — 对 `libei.so.*` 的 ctypes 绑定，绕过 CLI shim 取得微秒级延迟；以 `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei|cli|auto` 启用，默认在 libei 可加载时用 libei。
- **macOS Accessibility 强化** — 递归 `dump_accessibility_tree()` 与 polling `AccessibilityRecorder`，捕捉 focus / bounds 事件。
- **Android — adb shell 原语** — `AC_android_tap/swipe/key/text/screenshot` 直接通过 `adb` 驱动任何 USB / Wi-Fi adb 连接的手机，不需要常驻 daemon。
- **Android — uiautomator2 widget tree** — `AC_android_find_element/click_element/dump_hierarchy` 在 adb 路径之上加上 selector（`text` / `resource_id` / `description` / `class_name`）查找与实时 XML hierarchy dump。
- **iOS — WebDriverAgent / XCUITest** — 新的 `je_auto_control.ios.*` 命名空间：`tap`、`swipe`、`long_press`、`type_text`、`press_key`、`screenshot`、`screen_size`、`find_element` / `click_element`（XCUITest selector：`name`、`class_name`、`predicate`）、`dump_source`。新增七个 `AC_ios_*` executor 命令与对应 `ac_ios_*` MCP 工具。`facebook-wda` 为可选 pip 依赖、懒加载，非 macOS 主机 import 仍可成功。

**开发者体验**
- **autocontrol-lsp 完整化** — 追踪 `didOpen` / `didChange` / `didClose`、发布 JSON 与未知 `AC_*` 命令的 diagnostics、由即时的 executor 表生成 signature help。
- **`.pyi` stub 生成器** — `python -m je_auto_control.utils.stubs.generator je_auto_control/actions.pyi` 写出 IDE 端 stub 文件，所有 `AC_*` 命令在 IDE 内可 autocomplete 并显示参数提示。
- **VS Code 扩展** — 内置扩展新增 `AutoControl: Run / Screenshot / Preview` 命令，直接打本机 REST API。
- **浏览器扩展录制器** — `browser-extension/` 下的 Manifest V3 扩展：捕捉标签页的点击、输入、导航与表单提交，导出为 `AC_web_*` / `WR_*` JSON。
- **pytest plugin + Gherkin BDD** — `pytest11` entry point 自动加载；`@pytest.mark.autocontrol` 开启失败自动截屏；`bdd_steps.register_pytest_bdd_steps(pytest_bdd)` 一次把 `Given/When/Then` 对应到每一个 `AC_*` verb。
- **可视化流程编辑器** — node-based 视图与既有 list-based Script Builder 使用同一份 JSON 格式，互相兼容。

---
