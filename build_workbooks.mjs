import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const root = '/Users/xiaoyu/Documents/ale/repairs/build/2394-current-agent';
const task = path.join(root, 'task');
const renders = path.join(root, 'workbook-renders');
await fs.mkdir(renders, { recursive: true });
const head = { fill: '#3E556A', font: { bold: true, color: '#FFFFFF' }, wrapText: true };
const body = { wrapText: true, verticalAlignment: 'top', borders: { bottom: { style: 'thin', color: '#D7DFE7' } } };
function addSheet(book, name, rows, widths) {
  const sheet = book.worksheets.add(name);
  const range = sheet.getRangeByIndexes(0, 0, rows.length, widths.length);
  range.values = rows;
  range.format = body;
  sheet.getRangeByIndexes(0, 0, 1, widths.length).format = head;
  widths.forEach((width, index) => { sheet.getRangeByIndexes(0, index, rows.length, 1).format.columnWidth = width; });
  range.format.autofitRows();
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;
}
async function finish(book, label, output) {
  for (const sheet of book.worksheets.items) {
    const preview = await book.render({ sheetName: sheet.name, autoCrop: 'all', scale: 1.25, format: 'png' });
    await fs.writeFile(path.join(renders, `${label}-${sheet.name}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
  const errors = await book.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A', options: { useRegex: true, maxResults: 100 }, maxChars: 5000 });
  await fs.writeFile(path.join(renders, `${label}.errors.ndjson`), errors.ndjson, 'utf8');
  const structure = await book.inspect({ kind: 'sheet,table', include: 'id,name,values', tableMaxRows: 80, tableMaxCols: 8, maxChars: 38000 });
  await fs.writeFile(path.join(task, `${output}.inspect.ndjson`), structure.ndjson, 'utf8');
  const file = await SpreadsheetFile.exportXlsx(book);
  await file.save(path.join(task, output));
}

const answer = Workbook.create();
addSheet(answer, '交付物答案清单', [
  ['交付物名称', '固定路径/命名规则', '用途', '判定方式'],
  ['CRD Chart', 'output/charts/policy-crds', '交给平台发布人管理CRD生命周期', '运行Helm并检查Chart结构'],
  ['控制器Chart', 'output/charts/policy-controller', '交给平台发布人独立升级控制器', '运行Helm并检查Chart结构'],
  ['additive清单', 'output/rendered/additive.yaml', '保留旧新served版本', '解析YAML对象和版本字段'],
  ['prune清单', 'output/rendered/prune.yaml', '移除旧served版本', '解析YAML对象和版本字段'],
  ['bridge清单', 'output/rendered/bridge.yaml', '控制器兼容读取旧新版本', '解析YAML对象和环境变量'],
  ['steady清单', 'output/rendered/steady.yaml', '控制器只读v1', '解析YAML对象和环境变量'],
  ['渲染对象表', 'output/results/render_inventory.csv', '连接Chart模式与实际对象', '按复合主键核对'],
  ['所有权处理表', 'output/results/ownership_decisions.csv', '记录离线所有权快照的处理结论', '按cluster核对'],
  ['旧版本退场表', 'output/results/retirement_gate.csv', '记录离线存储证据的退场判断', '按cluster核对'],
  ['发布计划', 'output/results/release_plan.csv', '把阶段安排到已批准窗口', '按cluster和phase核对'],
  ['证据范围表', 'output/results/evidence_scope.csv', '区分离线快照与静态渲染', '按source_file核对'],
  ['Helm检查表', 'output/results/lint_results.csv', '记录两个Chart的lint结果', '按chart核对'],
  ['交接说明', 'output/README.txt', '说明候选包用途与结论边界', '读取正文'],
], [30, 72, 62, 56]);
addSheet(answer, '固定字段答案', [
  ['交付物或对象', '字段路径', '正确值', '来源与验证'],
  ['policy-crds', 'Chart.yaml的name', 'policy-crds', 'Chart边界'],
  ['policy-controller', 'Chart.yaml的name', 'policy-controller', 'Chart边界'],
  ['CRD', 'metadata.name', 'policies.policy.delivery.example', 'lifecycle_contract.json'],
  ['CRD', 'metadata.annotations.helm.sh/resource-policy', 'keep', '卸载保留合同'],
  ['CRD', 'spec.versions中storage=true的name', 'v1', 'lifecycle_contract.json'],
  ['CRD conversion', 'service.port', 443, 'lifecycle_contract.json的conversion_port'],
  ['bridge Deployment', 'READ_VERSIONS', 'v1alpha1、v1beta1、v1', 'lifecycle_contract.json的bridge_read_versions'],
  ['steady Deployment', 'READ_VERSIONS', 'v1', 'lifecycle_contract.json的steady_read_versions'],
  ['edge-eu1', 'ownership status和retirement status', 'READY和PASS', '两份快照按合同推导'],
  ['edge-us1', 'ownership status和retirement status', 'READY和HOLD', '对象未全部重写且仍含v1beta1'],
  ['edge-ap1', 'ownership status和retirement status', 'BLOCK和HOLD', '旧release未脱离'],
  ['edge-br1', 'ownership status和retirement status', 'BLOCK和HOLD', '接管未批准且存在转换失败'],
  ['全部快照结果', 'evidence_type', 'SNAPSHOT', '证据范围合同'],
], [38, 54, 74, 64]);
addSheet(answer, '固定集合答案', [
  ['交付物或对象', '字段或集合', '正确集合', '判定方式'],
  ['additive CRD', 'served版本', 'v1alpha1、v1beta1、v1', '集合精确匹配'],
  ['prune CRD', 'served版本', 'v1', '集合精确匹配'],
  ['bridge控制器', '读取版本', 'v1alpha1、v1beta1、v1', '集合精确匹配'],
  ['steady控制器', '读取版本', 'v1', '集合精确匹配'],
  ['控制器必需对象', 'kind', 'ServiceAccount、Service、Deployment', '必需集合包含'],
  ['控制器禁止对象', 'kind', 'CustomResourceDefinition、Policy', '交集必须为空'],
  ['所有权结果', 'cluster', 'edge-ap1、edge-br1、edge-eu1、edge-us1', '集合精确匹配'],
  ['阶段顺序', 'phase', 'ownership、additive、bridge、prune、steady', '按phase_order比较'],
], [36, 44, 88, 52]);
addSheet(answer, '固定数值答案', [
  ['交付物或对象', '字段或位置', '正确值', '容差', '来源与验证'],
  ['conversion Service', 'port', 443, 0, 'lifecycle_contract.json的conversion_port'],
  ['edge-eu1', 'total_objects', 126, 0, 'storage_snapshot.csv'],
  ['edge-us1', 'rewritten_to_v1', 79, 0, 'storage_snapshot.csv'],
  ['edge-br1', 'conversion_failures', 2, 0, 'storage_snapshot.csv'],
], [36, 42, 24, 22, 64]);
addSheet(answer, '允许变体答案', [
  ['对象', '允许变化', '不可变化', '判定方式'],
  ['Chart模板', '文件拆分、注释、辅助模板和取值组织可以变化', '两个release边界与合同语义不能变化', '实际执行Helm后解析对象'],
  ['Service引用', 'Service名称和命名空间可由一致的Chart取值决定', 'CRD引用必须与控制器Service闭合，端口为443', '跨清单比较名称、命名空间和端口'],
  ['YAML清单', '文档顺序、键序和空白可以变化', '对象主键、版本字段和环境变量不能变化', '结构化解析后比较'],
  ['CSV结果', '行序可以变化', '表头、业务主键和字段值不能变化', '按主键排序比较'],
  ['原因说明', '可使用含义相同的自然语言', '状态枚举和前置条件不能变化', '状态硬判，原因人工复核'],
], [34, 78, 88, 62]);
await finish(answer, '关键标准答案', '关键标准答案.xlsx');

const spec = Workbook.create();
addSheet(spec, '任务规格', [
  ['模块', '规格内容'],
  ['任务ID', 'policy_api_retirement_handoff'],
  ['主软件', 'Helm'],
  ['辅助工具', 'PowerShell7、Python3.12、UTF-8文本编辑器和CSV查看器'],
  ['输入来源', '平台发布组提供的生命周期合同、所有权快照、存储版本快照、发布窗口和现有Chart'],
  ['输入获取方式', '从输入数据包解压到本地只读目录'],
  ['原始输入文件', 'lifecycle_contract.json、ownership_snapshot.csv、storage_snapshot.csv、rollout_windows.csv与两个starter Chart目录'],
  ['目标输出文件', 'output/charts、output/rendered、output/results和output/README.txt'],
  ['核心操作链', '读取合同与快照→拆开Chart边界→渲染四种状态→检查对象与引用→判断所有权→判断退场→编排窗口'],
  ['CRD状态', 'additive保留旧新served版本，prune只保留v1；两个状态均以v1作为唯一storage版本'],
  ['控制器状态', 'bridge读取旧新三个版本，steady只读取v1；控制器Chart不生成CRD或Policy实例'],
  ['conversion闭合', 'CRD引用的Service名称、命名空间和端口必须能在控制器Chart的Service中定位'],
  ['所有权边界', 'legacy_helm需旧release已脱离且接管获批，manual需接管获批；判断只基于ownership_snapshot.csv'],
  ['退场条件', '所有权READY、对象全部重写、转换失败为0且storedVersions精确等于v1时允许prune与steady'],
  ['阶段与窗口', '阶段顺序为ownership、additive、bridge、prune、steady；结果使用rollout_windows.csv中的批准窗口'],
  ['证据口径', '输入CSV是离线快照，Helm输出是静态候选清单，均不代表集群实时运行状态'],
  ['实施回退', '实际变更窗口前重采集所有权与存储状态；条件回退时保留旧版本served并继续bridge，观察转换失败数和对象重写进度，恢复后另排窗口'],
  ['完成条件', '两个Chart可由Helm处理，四种状态清单与合同闭合，三张业务决策表和证据范围表可按输入复算'],
  ['可验证点', 'Chart名称、对象集合、API版本、served与storage布尔值、keep、conversion引用、状态枚举、阶段顺序和窗口主键'],
  ['不适合作为评分点的内容', 'YAML键序、文档顺序、模板拆分、注释、CSV行序、临时路径和文字排版'],
], [34, 136]);
await finish(spec, '任务规格转化', '任务规格转化.xlsx');
