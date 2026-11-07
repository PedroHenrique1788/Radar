"""Expose test failures as GitHub annotations without requiring private log access."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def escape(value):
    return value.replace('%','%25').replace('\r','%0D').replace('\n','%0A')


if __name__ == '__main__':
    path = Path(sys.argv[1])
    if not path.exists():
        print('::error::Pytest não gerou o relatório JUnit.')
        raise SystemExit(1)
    for case in ET.parse(path).getroot().iter('testcase'):
        for problem in list(case):
            if problem.tag in ('error','failure'):
                title = escape(case.get('name','Test failed')).replace(',', '%2C')
                text = escape((problem.text or problem.get('message','Failure'))[-12000:])
                print(f'::error title={title}::{text}')
