from threading import Lock

from je_auto_control.utils.exception.exception_tags import html_generate_no_data_tag_error_message
from je_auto_control.utils.exception.exceptions import AutoControlHTMLException
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.test_record.record_test_class import test_record_instance

_lock = Lock()

# HTML 模板 HTML template
_html_string = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"/>
    <title>AutoControl Report</title>
    <style>
        body {
            font-size: 100%;
        }
        h1 {
            font-size: 2em;
        }
        .main_table {
            margin: 0 auto;
            border-collapse: collapse;
            width: 75%;
            font-size: 1.5em;
        }
        .event_table_head {
            border: 3px solid #262626;
            background-color: aqua;
            font-family: "Times New Roman", sans-serif;
            text-align: center;
        }
        .failure_table_head {
            border: 3px solid #262626;
            background-color: #f84c5f;
            font-family: "Times New Roman", sans-serif;
            text-align: center;
        }
        .table_data_field_title {
            border: 3px solid #262626;
            background-color: #dedede;
            font-family: "Times New Roman", sans-serif;
            text-align: center;
            width: 25%;
        }
        .table_data_field_text {
            border: 3px solid #262626;
            background-color: #dedede;
            font-family: "Times New Roman", sans-serif;
            text-align: left;
            width: 75%;
        }
        .text {
            text-align: center;
            font-family: "Times New Roman", sans-serif;
        }
    </style>
</head>
<body>
<h1 class="text">Test Report</h1>
{event_table}
</body>
</html>
""".strip()

# 單一事件表格模板 Single event table template
_event_table = r"""
<table class="main_table">
    <thead>
        <tr>
            <th colspan="2" class="{table_head_class}">Test Report</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td class="table_data_field_title">function_name</td>
            <td class="table_data_field_text">{function_name}</td>
        </tr>
        <tr>
            <td class="table_data_field_title">param</td>
            <td class="table_data_field_text">{param}</td>
        </tr>
        <tr>
            <td class="table_data_field_title">time</td>
            <td class="table_data_field_text">{time}</td>
        </tr>
        <tr>
            <td class="table_data_field_title">exception</td>
            <td class="table_data_field_text">{exception}</td>
        </tr>
    </tbody>
</table>
<br>
""".strip()


def make_html_table(event_str: str, record_data: dict, table_head: str) -> str:
    """
    建立單一事件的 HTML 表格
    Create HTML table for a single event

    :param event_str: 現有的 HTML 字串 Existing HTML string
    :param record_data: 單一事件紀錄 Single event record
    :param table_head: 表頭樣式 (成功/失敗) Table head style
    :return: 更新後的 HTML 字串 Updated HTML string
    """
    return "".join([
        event_str,
        _event_table.format(
            table_head_class=table_head,
            function_name=record_data.get("function_name"),
            param=record_data.get("local_param"),
            time=record_data.get("time"),
            exception=record_data.get("program_exception"),
        )
    ])


def generate_html() -> str:
    """
    產生完整 HTML 報告字串
    Generate full HTML report string

    :return: HTML 字串 HTML string
    """
    autocontrol_logger.info("generate_html")

    if not test_record_instance.test_record_list:
        raise AutoControlHTMLException(html_generate_no_data_tag_error_message)

    event_str = ""
    for record_data in test_record_instance.test_record_list:
        # 判斷是否有例外，決定表格樣式
        if record_data.get("program_exception") == "None":
            event_str = make_html_table(event_str, record_data, "event_table_head")
        else:
            event_str = make_html_table(event_str, record_data, "failure_table_head")

    return _html_string.format(event_table=event_str)


def generate_html_report(html_name: str = "default_name") -> None:
    """
    輸出 HTML 報告檔案
    Output HTML report file

    :param html_name: 檔案名稱 (不含副檔名) File name without extension
    """
    autocontrol_logger.info(f"generate_html_report, html_name: {html_name}")

    new_html_string = generate_html()

    with _lock:  # 使用 with 確保 Lock 正確釋放 Ensure lock is released properly
        try:
            with open(html_name + ".html", "w+", encoding="utf-8") as file_to_write:
                file_to_write.write(new_html_string)
        except Exception as error:
            autocontrol_logger.error(
                f"generate_html_report failed, html_name: {html_name}, error: {repr(error)}"
            )