"""Search metadata, select one schema and demonstrate a disposable local tool view."""
# pylint: disable=invalid-name  # reason: numbered example filenames follow the repository catalog
import argparse
import json

import je_auto_control as ac


def main() -> None:
    """No server, remote session mutation or tool execution is needed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--query', default='screenshot')
    args = parser.parse_args()
    index = ac.default_tool_index()
    summaries = index.search(args.query)
    view = ac.ToolView(lambda: index)
    try:
        before = view.state()
        schema = None
        if summaries:
            name = summaries[0].name
            schema = index.get_schema(name).to_dict()
            view.enable([name])
        report = {'validated': True, 'summaries': [row.to_dict() for row in summaries],
                  'schema': schema, 'before': before, 'after': view.state(),
                  'page': view.list_page().to_dict(), 'native_operations': []}
    finally:
        view.close()
    print(json.dumps(report))


if __name__ == '__main__':
    main()
