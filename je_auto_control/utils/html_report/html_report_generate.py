import sys

from je_auto_control.utils.test_record.record_test_class import test_record
from je_auto_control.utils.exception.exceptions import HTMLException
from je_auto_control.utils.exception.exception_tag import html_generate_no_data_tag
from threading import Lock

lock = Lock()

html_string = \
    r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"/>
    <title>AutoControl Report</title>

    <style>
      
        body{{
            font-size: 100%;
        }}

        h1{{
            font-size: 2em;
        }}

        .main_table {{
            margin: 0 auto;
            border-collapse: collapse;
            width: 75%;
            font-size: 1.5em;
        }}

        .event_table_head {{
            border: 3px solid #262626;
            background-color: aqua;
            font-family: "Times New Roman", sans-serif;
            text-align: center;
        }}

        .table_data_field_title {{
            border: 3px solid #262626;
            padding: 0;
            margin: 0;
            background-color: #dedede;
            font-family: "Times New Roman", sans-serif;
            text-align: center;
            width: 25%;
        }}

        .table_data_field_text {{
            border: 3px solid #262626;
            padding: 0;
            margin: 0;
            background-color: #dedede;
            font-family: "Times New Roman", sans-serif;
            text-align: left;
            width: 75%;
        }}

        .text {{
            text-align: center;
            font-family: "Times New Roman", sans-serif;
        }}
    </style>
</head>
<body>
<h1 class="text">
    Test Report
</h1>
{event_table}
</body>
</html>
""".strip()

event_table = \
    r"""
    <table class="main_table">
        <thead>
        <tr>
            <th colspan="2" class="event_table_head">Test Report</th>
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


def generate_html(html_name: str = "default_name"):
    """
    :param html_name: save html file name
    :return: html_string
    """
    if len(test_record.total_record_list) == 0:
        raise HTMLException(html_generate_no_data_tag)
    else:
        event_str = ""
        for record_data in test_record.total_record_list:
            event_str = "".join(
                [
                    event_str,
                    event_table.format(
                        function_name=record_data.get("function_name"),
                        param=record_data.get("local_param"),
                        time=record_data.get("time"),
                        exception=record_data.get("program_exception"),
                    )
                ]
            )
        new_html_string = html_string.format(event_table=event_str)
        try:
            lock.acquire()
            with open(html_name + ".html", "w+") as file_to_write:
                file_to_write.write(
                    new_html_string
                )
        except Exception as error:
            print(repr(error), file=sys.stderr)
        finally:
            lock.release()
    return new_html_string
