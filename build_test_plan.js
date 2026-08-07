const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
        PageOrientation, LevelFormat } = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(text, width, opts = {}) {
    return new TableCell({
        borders,
        width: { size: width, type: WidthType.DXA },
        shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
            alignment: opts.align || AlignmentType.LEFT,
            children: [new TextRun({ text, bold: opts.bold || false, size: 21 })]
        })]
    });
}

function p(text, opts = {}) {
    return new Paragraph({
        spacing: { before: opts.before || 120, after: opts.after || 120 },
        alignment: opts.align || AlignmentType.LEFT,
        children: [new TextRun({ text, bold: opts.bold || false, size: opts.size || 22 })]
    });
}

function bullet(text, ref) {
    return new Paragraph({
        numbering: { reference: ref, level: 0 },
        spacing: { before: 60, after: 60 },
        children: [new TextRun({ text, size: 22 })]
    });
}

function numbered(text, ref) {
    return new Paragraph({
        numbering: { reference: ref, level: 0 },
        spacing: { before: 60, after: 60 },
        children: [new TextRun({ text, size: 22 })]
    });
}

const doc = new Document({
    styles: {
        default: { document: { run: { font: "Arial", size: 22 } } },
        paragraphStyles: [
            { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 36, bold: true, font: "Arial" },
              paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 } },
            { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 28, bold: true, font: "Arial" },
              paragraph: { spacing: { before: 200, after: 160 }, outlineLevel: 1 } },
            { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 24, bold: true, font: "Arial" },
              paragraph: { spacing: { before: 160, after: 120 }, outlineLevel: 2 } },
        ]
    },
    numbering: {
        config: [
            { reference: "bullets",
              levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
                style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
            { reference: "numbers",
              levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
                style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
        ]
    },
    sections: [{
        properties: {
            page: {
                size: { width: 11906, height: 16838 },
                margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
            }
        },
        children: [
            new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 240 },
                children: [new TextRun({ text: "PicMeasure 实物测试方案", bold: true, size: 44 })]
            }),
            new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 480 },
                children: [new TextRun({ text: "基于 4 cm 橘红色参考球的点击式树枝长度测量", size: 28 })]
            }),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("1 测试目的")] }),
            p("本方案用于验证 PicMeasure 在真实场景下的测量精度、重复性及可用性。软件通过检测已知直径（4 cm）的橘红色参考球建立像素-厘米比例尺，再由操作者在图像上点击折线测量树枝长度。测试将围绕以下目标展开："),
            bullet("验证参考球检测在不同光照、角度、遮挡条件下的鲁棒性；", "bullets"),
            bullet("评估单根树枝长度的测量误差与操作者点击偏差的关系；", "bullets"),
            bullet("评估多分支、不同粗细、不同曲率树枝的测量一致性；", "bullets"),
            bullet("给出可接受的拍摄与操作规范，确保现场复测精度。", "bullets"),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("2 被测软件信息")] }),
            new Table({
                width: { size: 9360, type: WidthType.DXA },
                columnWidths: [2800, 6560],
                rows: [
                    new TableRow({ children: [cell("软件名称", 2800, { bold: true, fill: "D5E8F0" }), cell("PicMeasure v0.3.0", 6560)] }),
                    new TableRow({ children: [cell("核心功能", 2800, { bold: true, fill: "D5E8F0" }), cell("参考球自动检测 + 点击折线测长", 6560)] }),
                    new TableRow({ children: [cell("参考物", 2800, { bold: true, fill: "D5E8F0" }), cell("直径 4 cm 橘红色球体（默认配置）", 6560)] }),
                    new TableRow({ children: [cell("输出单位", 2800, { bold: true, fill: "D5E8F0" }), cell("cm", 6560)] }),
                    new TableRow({ children: [cell("主要命令", 2800, { bold: true, fill: "D5E8F0" }), cell("calibrate（标定）、click-measure（测量）", 6560)] }),
                    new TableRow({ children: [cell("运行环境", 2800, { bold: true, fill: "D5E8F0" }), cell("Windows 可执行文件（dist/picmeasure/picmeasure.exe）", 6560)] }),
                ]
            }),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("3 测试原理与误差来源")] }),
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("3.1 测量原理")] }),
            p("软件以 HSV 颜色阈值 + Hough 圆检测定位参考球，得到球的像素半径 r，并按公式计算比例尺："),
            p("pixels_per_cm = 2 × r / 4.0", { align: AlignmentType.CENTER, bold: true }),
            p("操作者沿树枝点击得到顶点序列 (x1,y1)...(xn,yn)，软件累加欧氏距离得到像素长度 Lpx，再换算为："),
            p("Lcm = Lpx / pixels_per_cm", { align: AlignmentType.CENTER, bold: true }),

            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("3.2 主要误差来源")] }),
            new Table({
                width: { size: 9360, type: WidthType.DXA },
                columnWidths: [2200, 4200, 2960],
                rows: [
                    new TableRow({ children: [
                        cell("误差来源", 2200, { bold: true, fill: "D5E8F0" }),
                        cell("影响说明", 4200, { bold: true, fill: "D5E8F0" }),
                        cell("控制/评估方法", 2960, { bold: true, fill: "D5E8F0" }),
                    ]}),
                    new TableRow({ children: [
                        cell("参考球检测", 2200),
                        cell("Hough 圆心、半径估计偏差直接决定比例尺。", 4200),
                        cell("与真实直径对比，记录 confidence。", 2960),
                    ]}),
                    new TableRow({ children: [
                        cell("拍摄透视畸变", 2200),
                        cell("球或树枝距镜头光轴较远时像素比例尺不均匀。", 4200),
                        cell("球尽量靠近被测树枝，镜头正对目标。", 2960),
                    ]}),
                    new TableRow({ children: [
                        cell("操作者点击", 2200),
                        cell("顶点未落在树枝中心轴线，或折线欠采样导致曲线被低估。", 4200),
                        cell("同一人多次测量、多人交叉测量。", 2960),
                    ]}),
                    new TableRow({ children: [
                        cell("树枝遮挡/交叉", 2200),
                        cell("目标树枝被叶片或邻近枝条遮挡，折线无法贴合真实走向。", 4200),
                        cell("选择清晰、无遮挡样本，剔除严重遮挡数据。", 2960),
                    ]}),
                    new TableRow({ children: [
                        cell("图像分辨率", 2200),
                        cell("球半径像素过小会降低比例尺精度。", 4200),
                        cell("保证球半径 ≥ 20 px，建议 ≥ 40 px。", 2960),
                    ]}),
                ]
            }),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("4 测试环境与器材")] }),
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("4.1 硬件")] }),
            bullet("橘红色标准球：直径 4 cm（可用喷涂/贴纸乒乓球或 3D 打印球替代，误差 ≤ 0.5 mm）。", "bullets"),
            bullet("卷尺/钢直尺：精度 1 mm，用于获取地面真值长度。", "bullets"),
            bullet("游标卡尺：用于复核球的实际直径。", "bullets"),
            bullet("固定支架：保持树枝在拍摄期间不发生位移，便于重复拍摄。", "bullets"),
            bullet("数码相机或手机：建议 1200 万像素以上，关闭美颜、HDR、自动畸变校正。", "bullets"),
            bullet("标记笔/标签纸：对测试树枝编号。", "bullets"),

            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("4.2 软件与数据")] }),
            bullet("Windows 测试机（Win10/Win11 64 位）。", "bullets"),
            bullet("PicMeasure 可执行包：dist/picmeasure/ 文件夹。", "bullets"),
            bullet("数据记录表：见附录 A。", "bullets"),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("5 测试样本设计")] }),
            p("建议准备 3 类样本，每类不少于 5 根，共 15–20 根："),
            new Table({
                width: { size: 9360, type: WidthType.DXA },
                columnWidths: [1800, 2800, 2400, 2360],
                rows: [
                    new TableRow({ children: [
                        cell("类别", 1800, { bold: true, fill: "D5E8F0" }),
                        cell("特征", 2800, { bold: true, fill: "D5E8F0" }),
                        cell("真值获取方式", 2400, { bold: true, fill: "D5E8F0" }),
                        cell("考察目标", 2360, { bold: true, fill: "D5E8F0" }),
                    ]}),
                    new TableRow({ children: [
                        cell("直枝", 1800),
                        cell("近似直线，长度 20–60 cm，直径 5–15 mm。", 2800),
                        cell("钢直尺/卷尺直接量取。", 2400),
                        cell("比例尺精度、点击偏差。", 2360),
                    ]}),
                    new TableRow({ children: [
                        cell("曲枝", 1800),
                        cell("明显弯曲，长度 30–80 cm。", 2800),
                        cell("软尺沿枝条贴合测量。", 2400),
                        cell("折线采样密度对曲线长度的影响。", 2360),
                    ]}),
                    new TableRow({ children: [
                        cell("短枝/分叉枝", 1800),
                        cell("长度 10–30 cm，存在分叉或细枝。", 2800),
                        cell("游标卡尺 + 分段卷尺。", 2400),
                        cell("小目标测量稳定性、分叉处判定一致性。", 2360),
                    ]}),
                ]
            }),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("6 测试步骤")] }),
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("6.1 拍摄规范")] }),
            numbered("将参考球悬挂/固定在树枝旁，球心与目标树枝处于同一景深平面，距离镜头 1.0–2.5 m。", "numbers"),
            numbered("镜头光轴尽量垂直于树枝所在平面，避免大角度俯仰。", "numbers"),
            numbered("保证参考球在画面中完整、清晰，球半径像素值 ≥ 20 px（建议 ≥ 40 px）。", "numbers"),
            numbered("同一目标连续拍摄 3 张（轻微平移/重新对焦），用于重复性测试。", "numbers"),
            numbered("记录场景光照、拍摄距离、相机型号、参考球实际直径。", "numbers"),

            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("6.2 标定检测测试（calibrate）")] }),
            numbered("在命令行运行：picmeasure.exe calibrate <图片路径> --verbose", "numbers"),
            numbered("记录输出 JSON 中的 detected、ball_center_xy、ball_radius_px、pixels_per_unit、confidence。", "numbers"),
            numbered("对所有测试图片执行上述操作，统计 ball_radius_px 的变异系数（CV）。", "numbers"),
            numbered("若 confidence < 0.3 或 ball_radius_px < 20 px，标记该图片为“不可靠”，不计入精度统计。", "numbers"),

            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("6.3 长度测量测试（click-measure）")] }),
            numbered("运行：picmeasure.exe click-measure <图片路径> -o output/<样本号>.json", "numbers"),
            numbered("操作者 A 沿单根目标树枝中心轴线点击折线，顶点间距 2–5 cm，曲线处加密。", "numbers"),
            numbered("按 's' 保存并退出，记录 JSON 中的 length_units。", "numbers"),
            numbered("同一操作者对该图片重复测量 3 次（每次重新打开软件，不参考前次结果）。", "numbers"),
            numbered("换操作者 B 重复步骤 2–4。", "numbers"),
            numbered("对同一目标的 3 张不同照片分别测量，评估拍摄重复性。", "numbers"),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("7 评价指标")] }),
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("7.1 参考球检测指标")] }),
            new Table({
                width: { size: 9360, type: WidthType.DXA },
                columnWidths: [2600, 2600, 4160],
                rows: [
                    new TableRow({ children: [
                        cell("指标", 2600, { bold: true, fill: "D5E8F0" }),
                        cell("计算方法", 2600, { bold: true, fill: "D5E8F0" }),
                        cell("合格标准", 4160, { bold: true, fill: "D5E8F0" }),
                    ]}),
                    new TableRow({ children: [
                        cell("检测成功率", 2600),
                        cell("detected=true 的图片数 / 总图片数", 2600),
                        cell("≥ 95%（在规范拍摄条件下）", 4160),
                    ]}),
                    new TableRow({ children: [
                        cell("比例尺重复性", 2600),
                        cell("同一场景 3 张照片 pixels_per_unit 的标准差 / 均值", 2600),
                        cell("CV ≤ 2%", 4160),
                    ]}),
                    new TableRow({ children: [
                        cell("球半径像素", 2600),
                        cell("输出 JSON 中的 ball_radius_px", 2600),
                        cell("≥ 20 px，建议 ≥ 40 px", 4160),
                    ]}),
                    new TableRow({ children: [
                        cell("置信度", 2600),
                        cell("输出 JSON 中的 confidence", 2600),
                        cell("≥ 0.3（默认值）", 4160),
                    ]}),
                ]
            }),

            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("7.2 长度测量指标")] }),
            new Table({
                width: { size: 9360, type: WidthType.DXA },
                columnWidths: [2600, 2600, 4160],
                rows: [
                    new TableRow({ children: [
                        cell("指标", 2600, { bold: true, fill: "D5E8F0" }),
                        cell("计算方法", 2600, { bold: true, fill: "D5E8F0" }),
                        cell("合格标准", 4160, { bold: true, fill: "D5E8F0" }),
                    ]}),
                    new TableRow({ children: [
                        cell("绝对误差", 2600),
                        cell("E = Lmeas − Ltrue", 2600),
                        cell("|E| ≤ 1 cm 或 |E| ≤ 2%·Ltrue（取较大者）", 4160),
                    ]}),
                    new TableRow({ children: [
                        cell("相对误差", 2600),
                        cell("RE = |E| / Ltrue × 100%", 2600),
                        cell("RE ≤ 5%（直枝）；RE ≤ 8%（曲枝）", 4160),
                    ]}),
                    new TableRow({ children: [
                        cell("重复性（组内）", 2600),
                        cell("同一操作者 3 次测量结果的标准差 / 均值", 2600),
                        cell("CV ≤ 3%", 4160),
                    ]}),
                    new TableRow({ children: [
                        cell("再现性（组间）", 2600),
                        cell("不同操作者测量结果的标准差 / 均值", 2600),
                        cell("CV ≤ 5%", 4160),
                    ]}),
                    new TableRow({ children: [
                        cell("拍摄重复性", 2600),
                        cell("同一场景 3 张照片测量均值与真值误差", 2600),
                        cell("RE ≤ 5%", 4160),
                    ]}),
                ]
            }),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("8 数据记录与分析")] }),
            p("所有原始数据按附录 A 表格记录。分析脚本可用 Python/pandas 完成，建议输出："),
            bullet("每张图片的 ball_radius_px、confidence、pixels_per_unit；", "bullets"),
            bullet("每根树枝的真值、各次测量值、绝对误差、相对误差；", "bullets"),
            bullet("按类别（直/曲/短枝）分组的误差均值、标准差、最大误差；", "bullets"),
            bullet("Bland-Altman 图或误差箱线图，识别异常样本。", "bullets"),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("9 缺陷判定与处理")] }),
            new Table({
                width: { size: 9360, type: WidthType.DXA },
                columnWidths: [2200, 4200, 2960],
                rows: [
                    new TableRow({ children: [
                        cell("现象", 2200, { bold: true, fill: "D5E8F0" }),
                        cell("可能原因", 4200, { bold: true, fill: "D5E8F0" }),
                        cell("处理建议", 2960, { bold: true, fill: "D5E8F0" }),
                    ]}),
                    new TableRow({ children: [
                        cell("球检测失败", 2200),
                        cell("光照过暗/过曝、球被遮挡、颜色阈值不匹配、球太小。", 4200),
                        cell("重拍、调整 HSV 阈值、增大球直径或换颜色更饱和的球。", 2960),
                    ]}),
                    new TableRow({ children: [
                        cell("测量值系统性偏大/偏小", 2200),
                        cell("球实际直径与配置不符、镜头畸变大、球不在目标平面。", 4200),
                        cell("复核球径、调整拍摄距离与角度、更新 known_diameter_cm。", 2960),
                    ]}),
                    new TableRow({ children: [
                        cell("曲枝明显偏小", 2200),
                        cell("折线顶点数不足，直线近似低估了曲线长度。", 4200),
                        cell("在曲线处加密点击，顶点间距 ≤ 2 cm。", 2960),
                    ]}),
                    new TableRow({ children: [
                        cell("操作者间差异大", 2200),
                        cell("对树枝起点/终点、分叉处判定不一致。", 4200),
                        cell("制定统一标注规范，必要时在图片上预先标记测量区间。", 2960),
                    ]}),
                ]
            }),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("10 测试报告模板")] }),
            p("测试完成后应输出一份报告，至少包含："),
            numbered("测试环境：硬件、软件版本、拍摄参数；", "numbers"),
            numbered("样本清单：编号、类别、真值、照片数量；", "numbers"),
            numbered("标定结果汇总：检测成功率、pixels_per_unit 分布、异常图片说明；", "numbers"),
            numbered("测量精度汇总：按类别的误差均值、最大误差、CV；", "numbers"),
            numbered("结论：是否满足合格标准、可用场景与限制条件；", "numbers"),
            numbered("附录：原始数据表、标注图示例。", "numbers"),

            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("附录 A：数据记录表（示例）")] }),
            p("表 A-1 参考球标定记录", { bold: true }),
            new Table({
                width: { size: 9360, type: WidthType.DXA },
                columnWidths: [1560, 1560, 1560, 1560, 1560, 1560],
                rows: [
                    new TableRow({ children: [
                        cell("图片编号", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("球实际直径(cm)", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("ball_radius_px", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("pixels_per_unit", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("confidence", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("是否合格", 1560, { bold: true, fill: "E8F0D5" }),
                    ]}),
                    new TableRow({ children: [
                        cell("IMG_001", 1560),
                        cell("4.0", 1560),
                        cell("", 1560),
                        cell("", 1560),
                        cell("", 1560),
                        cell("", 1560),
                    ]}),
                    new TableRow({ children: [
                        cell("IMG_002", 1560),
                        cell("4.0", 1560),
                        cell("", 1560),
                        cell("", 1560),
                        cell("", 1560),
                        cell("", 1560),
                    ]}),
                ]
            }),
            p("表 A-2 树枝长度测量记录", { bold: true, before: 240 }),
            new Table({
                width: { size: 9360, type: WidthType.DXA },
                columnWidths: [1560, 1560, 1560, 1560, 1560, 1560],
                rows: [
                    new TableRow({ children: [
                        cell("样本编号", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("类别", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("真值(cm)", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("测量均值(cm)", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("绝对误差(cm)", 1560, { bold: true, fill: "E8F0D5" }),
                        cell("相对误差(%)", 1560, { bold: true, fill: "E8F0D5" }),
                    ]}),
                    new TableRow({ children: [
                        cell("B-01", 1560),
                        cell("直枝", 1560),
                        cell("", 1560),
                        cell("", 1560),
                        cell("", 1560),
                        cell("", 1560),
                    ]}),
                    new TableRow({ children: [
                        cell("B-02", 1560),
                        cell("曲枝", 1560),
                        cell("", 1560),
                        cell("", 1560),
                        cell("", 1560),
                        cell("", 1560),
                    ]}),
                ]
            }),
        ]
    }]
});

Packer.toBuffer(doc).then(buffer => {
    fs.writeFileSync("PicMeasure_实物测试方案.docx", buffer);
    console.log("Generated PicMeasure_实物测试方案.docx");
});
