# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Read in a .xls file and generate a units module for OpenHTF.

UNECE, the United Nations Economic Commision for Europe, publishes a set of
unit codes for international trade in the form of Excel spreadsheets (.xls
files). Various revisions of the spreadsheet can be found as part of the the
downloadable "Codes for Units of Measurement used in the International Trade"
.zip archive listed here:

http://www.unece.org/cefact/codesfortrade/codes_index.html

This tool is used to parse those spreadsheets and turn the published standard
code set into a sub-module inside OpenHTF.

Typical usage of this generation script looks like:

python units_from_xls.py ~/Downloads/rec20_Rev9e_2014.xls

If this file is run from its home in the OpenHTF source tree, the default
behavior will be to overwrite the units submodule in the same source tree. The
output path can be overridden if desired (see command help for details).

Legal python names are generated for the UnitDescriptor objects from the "Name"
field on the spreadsheet, generally by removing special characters, turning
spaces into underscores, and coverting to uppercase.
"""


import argparse
import os
import shutil
import re
import sys
from tempfile import mkstemp

import xlrd


# Column names for the columns we care about. This list must be populated in
# the expected order: [<name label>, <code label>, <suffix label>].
COLUMN_NAMES = ['Name',
                'Common\nCode',
                'Symbol']

PRE = '''# coding: utf-8
# THIS FILE IS AUTOMATICALLY GENERATED. DO NOT EDIT.

# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Units of measure for OpenHTF.

THIS FILE IS AUTOMATICALLY GENERATED. DO NOT EDIT.

Used to retrieve UNECE unit codes by object, name, or suffix:

    from openhtf.util import units

    # The following three lines are equivalent:
    @measures(units.METRE_PER_SECOND)
    @measures(units.Unit('m/s'))
    @measures(units.Unit('metre per second'))

OpenHTF uses UNECE unit codes internally because they are relatively complete
and modern, and because they are recognized internationally. For full details
regarding where we get the codes from and which units are avaiable, see the
docstring at the top of openhtf/util/units/bin/units_from_xls.py.

THIS FILE IS AUTOMATICALLY GENERATED. DO NOT EDIT.
"""


import collections


UnitDescriptor = collections.namedtuple('UnitDescriptor', 'name code suffix')

ALL_UNITS = []


# NO_DIMENSION means that there are units set, but they cannot be expressed
# by a known dimension (such as a ratio)
NO_DIMENSION = UnitDescriptor('No dimension', 'NDL', None)
ALL_UNITS.append(NO_DIMENSION)
NONE = UnitDescriptor('None', None, None)
ALL_UNITS.append(NONE)
'''

POST = '''
# Convenience aliases.
MINUTE = MINUTE_UNIT_OF_TIME
SECOND = SECOND_UNIT_OF_TIME


class UnitLookup(object):
  """Facilitates user-friendly access to units."""
  def __init__(self, lookup):
    self._lookup = lookup

  def __call__(self, name_or_suffix):
    """Provides instantiation-like access for units module."""
    return self._lookup[name_or_suffix]


UNITS_BY_NAME = {u.name: u for u in ALL_UNITS}
UNITS_BY_SUFFIX = {u.suffix: u for u in ALL_UNITS}

del ALL_UNITS

UNITS_BY_ALL = {}
UNITS_BY_ALL.update(UNITS_BY_NAME)
UNITS_BY_ALL.update(UNITS_BY_SUFFIX)

Unit = UnitLookup(UNITS_BY_ALL)
'''

SHEET_NAME = 'Annex II & Annex III'
UNIT_KEY_REPLACEMENTS = {' ': '_',
                         ',' : '_',
                         '.': '_',
                         '-': '_',
                         '/': '_PER_',
                         '%': 'PERCENT',
                         '[': '',
                         ']': '',
                         '(': '',
                         ')': '',
                         "'": '',
                         '8':  'EIGHT',
                         '15': 'FIFTEEN',
                         '30': 'THIRTY',
                         '\\': '_',
                         unichr(160): '_',
                         unichr(176): 'DEG_',
                         unichr(186): 'DEG_',
                         unichr(8211): '_',
                        }


def main():
  """Main entry point for UNECE code .xls parsing."""
  parser = argparse.ArgumentParser(
      description='Reads in a .xls file and generates a units module for '
                  'OpenHTF.',
      prog='python units_from_xls.py')
  parser.add_argument('xlsfile', type=str,
                      help='the .xls file to parse')
  parser.add_argument(
      '--outfile',
      type=str,
      default=os.path.join(os.path.dirname(__file__), os.path.pardir, 'util',
                           'units.py'),
      help='where to put the generated .py file.')
  args = parser.parse_args()

  if not os.path.exists(args.xlsfile):
    print 'Unable to locate the file "%s".' % args.xlsfile
    parser.print_help()
    sys.exit()

  unit_defs = unit_defs_from_sheet(
      xlrd.open_workbook(args.xlsfile).sheet_by_name(SHEET_NAME),
      COLUMN_NAMES)

  _, tmp_path = mkstemp()
  with open(tmp_path, 'w') as new_file:
    new_file.write(PRE)
    new_file.writelines(
        [line.encode('utf8', 'replace') for line in unit_defs])
    new_file.write(POST)
    new_file.flush()

  os.remove(args.outfile)
  shutil.move(tmp_path, args.outfile)


def unit_defs_from_sheet(sheet, column_names):
  """A generator that parses a worksheet containing UNECE code definitions.

  Args:
    sheet: An xldr.sheet object representing a UNECE code worksheet.
    column_names: A list/tuple with the expected column names corresponding to
                  the unit name, code and suffix in that order.
  Yields: Lines of Python source code that define OpenHTF Unit objects.
  """
  seen = set()
  try:
    col_indices = {}
    rows = sheet.get_rows()
    
    # Find the indices for the columns we care about.
    for idx, cell in enumerate(rows.next()):
      if cell.value in column_names:
        col_indices[cell.value] = idx

    # loop over all remaining rows and pull out units.
    for row in rows:
      name = row[col_indices[column_names[0]]].value.replace("'", r'\'')
      code = row[col_indices[column_names[1]]].value
      suffix = row[col_indices[column_names[2]]].value.replace("'", r'\'')
      key = unit_key_from_name(name)
      if key in seen:
        continue
      seen.add(key)

      yield "%s = UnitDescriptor('%s', '%s', '''%s''')\n" % (
          key, name, code, suffix)
      yield "ALL_UNITS.append(%s)\n" % key

  except xlrd.XLRDError:
    sys.stdout.write('Unable to process the .xls file.')


def unit_key_from_name(name):
  """Return a legal python name for the given name for use as a unit key."""
  result = name

  for old, new in UNIT_KEY_REPLACEMENTS.iteritems():
    result = result.replace(old, new)

  # Collapse redundant underscores and convert to uppercase.
  result = re.sub(r'_+', '_', result.upper())

  return result


if __name__ == '__main__':
  main()
