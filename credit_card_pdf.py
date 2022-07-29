from beancount.ingest.importers.mixins import filing, identifier
import os
import collections
import datetime
import dateutil
import subprocess
from beancount.core import data, flags
from beancount.core.amount import Amount
from beancount.core.number import ZERO, D
from categorisers.lloyds_credit import TransactionCategoriser
from beancount.utils.date_utils import parse_date_liberally

# class Importer(identifier.IdentifyMixin, filing.FilingMixin):
class Importer(filing.FilingMixin):
    """
        Description:
        Imports the PDF files of monthly Lloyds credit card statements. Can
        also take the output of pdf2txt.py on such a file, to allow the PDFs to
        be preparsed to help reduce processing time (likely to be of use during development of this parser)

        Transactions are initially marked with the WARN flag ('!' in beancount
        syntax), with the expectation that the categoriser change the flag to
        OK ('*' in beancount syntax) for identified transactions.

        System requirements:
         * There needs to be an implementation of 'file(1)' available which can detect and identify PDF files.
         * There also needs to be 'pdf2txt.py' which extracts the text fields found in a PDF.
    """
    def parse_amount(self, string):
        return D(string)

    def file_name(self, file):
        if file.name.endswith('.txt'):
            extension = 'txt'
        else:
            extension = 'pdf'
        return (
            super()
            .file_name(file)
            .replace(
                os.path.basename(file.name),
                f"card-{self.an_suffix}-statement.{extension}"
            )
        )

    def file_date(self, file):
        "Return the period end, found on the Statement Date line"
        try:
            if self.pages is None:
                if file.name.endswith('.txt'):
                    f = open(file.name)
                    txt = f.read().encode('utf-8')
                    self.pages = list(map(lambda page: page.split(b"\n"), txt.split(b"\f")))
                else:
                    self.pages = self._to_text(file)
                if self.pages is None:
                    return
            line_before_date = self.pages[0].index(b'Your credit card statement')
            date_line = self.pages[0][line_before_date+1]
            date = parse_date_liberally( date_line )
            return date
        except IndexError:
            pass


    def identify(self, file):
        try:
            if self.file_date(file) is None:
                return False
            if self.pages is None:
                return False
            # When the credit card was the "Duo", the values in the table appear immediately after the field name (in field order of the extracted pdf)
            if self.pages[0].count(b'Lloyds Bank Avios Rewards') > 0 or self.pages[0].count(b'Lloyds Bank Cashback') > 0:
                marker_idx = self.pages[0].index(b"Next month's estimated interest")
                # print(f'DBG: marker index is {marker_idx}', file=os.sys.stderr)
                # print(f'DBG: marker line is {self.pages[0][marker_idx]}', file=os.sys.stderr)
                # print(f'DBG: next few fields are {self.pages[0][marker_idx-20:marker_idx+20]}', file=os.sys.stderr)
                header_line = self.pages[0][marker_idx+2].decode('utf-8')
                # print(f'DBG: I think this is the header line: >{header_line}<', file=os.sys.stderr)
            elif self.pages[0].count(b'Lloyds Bank Duo Avios') > 0:
                marker_idx = self.pages[0].index(b"Mastercard [M] Card Number")
                # print(f'DBG: marker index is {marker_idx}', file=os.sys.stderr)
                # print(f'DBG: marker line is {self.pages[0][marker_idx]}', file=os.sys.stderr)
                # print(f'DBG: next few fields are {self.pages[0][marker_idx-2:marker_idx+2]}', file=os.sys.stderr)
                header_line = self.pages[0][marker_idx+1].decode('utf-8')
                # print(f'DBG: I think this is the header line: >{header_line}<', file=os.sys.stderr)
            else:
                return False
            if header_line[15:20] == self.an_suffix:
                return True
            return False
        except UnicodeDecodeError:
            return None

    # def call_categorizer(self, txn, row):
    def call_categorizer(self, txn):
        if not isinstance(self.categorizer, collections.abc.Callable):
            return txn
        return self.categorizer(txn)


    def extract(self, file, existing_entries=None):
        entries = []
        # We use this when we create the balance-carried-forward and the
        # cashback-earned txns at the end of the run. We have to process the
        # main txns first in order to capture the first date

        # First two pages can be skipped (first page is credit summary, due
        # date, address label etc; second page is the list of standing charges)

        txn_page = self.pages[2]

        def fix_price(p):
            """ convert to a string (from binary), strip leading space, and add a leading '-' if it ends in 'CR'"""
            s = p.decode('utf-8').strip()
            if s.endswith('CR'):
                return f'-{s[0:-2]}'
            return s
 
        try:
            desc_label_idx = txn_page.index(b'Description')
            amt_label_idx = txn_page.index(b'Amount \xc2\xa3')
            new_bal_label_idx = txn_page.index(b'New balance')

            txn_count = new_bal_label_idx - desc_label_idx - 3
            if amt_label_idx < new_bal_label_idx:
                # print('Path AA', file=os.sys.stderr)
                dates = txn_page[desc_label_idx+4:desc_label_idx+4+txn_count]
                txn_count -= 2
                if txn_page[new_bal_label_idx+(3*txn_count)+7].startswith(b' '):
                    # print('Path BB', file=os.sys.stderr)
                    # We don't have ISO3166 3-letter country codes
                    amts = txn_page[new_bal_label_idx+(3*txn_count)+7:new_bal_label_idx+(4*txn_count)+7]
                else:
                    # print('Path CC', file=os.sys.stderr)
                    # We do have ISO3166 3-letter country codes
                    # Unfortunately we don't have them for all transactions and there's no easy way to work out to which txn a given code belongs.
                    # We therefore have to skip them all. The txn amounts start with a load of b' ' bytes so we look for that.
                    amt_start_idx = new_bal_label_idx + (3*txn_count) + 7
                    # print(f'Debug: the next few fields are {txn_page[amt_start_idx:amt_start_idx+txn_count+5]}', file=os.sys.stderr)
                    while not txn_page[amt_start_idx].startswith(b'  '):
                        # print('Path DD', file=os.sys.stderr)
                        amt_start_idx += 1
                    # amts = txn_page[amt_start_idx:amt_start_idx+txn_count+1]
                    amts = txn_page[amt_start_idx+1:]
                    while amts.count(b'') > 0:
                        amts.remove(b'')
                    amts = amts[0:txn_count]
            else:
                # print('Path EE', file=os.sys.stderr)
                dates = txn_page[desc_label_idx+2:desc_label_idx+2+txn_count]
                amts = txn_page[amt_label_idx+4:amt_label_idx+(txn_count)+4]
            amts = list(map(fix_price, amts))
            dates2 = txn_page[new_bal_label_idx+2:new_bal_label_idx+2+txn_count]
            if txn_page[new_bal_label_idx+5+txn_count] == b'A' or txn_page[new_bal_label_idx+5+txn_count] == b'M':
                print("Path FF: ", file=os.sys.stderr)
                cards = txn_page[new_bal_label_idx+txn_count+2:4+new_bal_label_idx+(2*txn_count)]
                desc = txn_page[new_bal_label_idx+(2*txn_count)+4:new_bal_label_idx+(3*txn_count)+4]
                payees = txn_page[new_bal_label_idx+(3*txn_count)+4:new_bal_label_idx+(4*txn_count)+4]
            else:
                print("Path GG", file=os.sys.stderr)
                desc = txn_page[new_bal_label_idx+txn_count+4:4+new_bal_label_idx+(2*txn_count)]
                payees = txn_page[new_bal_label_idx+(2*txn_count)+4:new_bal_label_idx+(3*txn_count)+4]
                cards = [None]*txn_count

        except ValueError:
            return []

        # if desc[0] == b'':
        #     payees.insert(0, b'')
        #     cards.insert(0, b'')

        print(f'The page is this: {txn_page}', file=os.sys.stderr)
        print(f'some dates: {dates}', file=os.sys.stderr)
        print(f'other dates: {dates2}', file=os.sys.stderr)
        print(f'descriptions: {desc}', file=os.sys.stderr)
        print(f'cards: {cards}', file=os.sys.stderr)
        print(f'payees: {payees}', file=os.sys.stderr)
        print(f'prices: {amts}', file=os.sys.stderr)
        tuples = list(zip(dates, dates2, desc, payees, amts,cards))
        file_date = self.file_date(file)

        for i in tuples:
            print(f"Looking at a txn: {i}", file=os.sys.stderr)
            payee = i[2].decode('utf-8')
            narration = i[3].decode('utf-8')
            tags = set([])
            links = data.EMPTY_SET
            meta = data.new_metadata(file.name, i)
            if i[5] is not None:
                meta['card'] = i[5].decode('utf-8')
            y = file_date.year
            if file_date.month == 1 and 'DECEMBER' in i[0].decode('utf-8'):
               y -= 1
            date = parse_date_liberally(i[0].decode('utf-8')+ ' ' + str(y))
            txn = data.Transaction(meta, date, self.FLAG, payee, narration, tags, links, [])
            txn = self.call_categorizer(txn)
            units = Amount(-self.parse_amount(i[4]), self.currency)
            txn.postings.append(
                    data.Posting(self.filing_account, units, None, None, None, None))

            entries.append(txn)

        return entries

    @staticmethod
    def is_month(month_name):
        return month_name in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    def _to_text(self, file):
        """ 
        returns a list of lists where the outer lists are split by page and the
        inner list items are split into text fields (called here 'records')

        [
          [ record0, record1, record2, record3, ... ],
          [ record0, record1, record2, record3, ... ],
          ...
        ]

        """
        check_type = subprocess.check_output(['file', file.name ])
        if b'PDF document' not in check_type:
            return None
        try:
            txt = subprocess.check_output(['pdf2txt.py', file.name ])
            self.pages = list(map(lambda page: page.split(b"\n"), txt.split(b"\f")))
            return self.pages
        except subprocess.CalledProcessError:
            return None

    def __init__(self, account, an_suffix, skip_balances=True):
        self.filing_account = account
        self.an_suffix = an_suffix
        self.skip_balances = skip_balances
        self.FLAG = flags.FLAG_WARNING
        self.categorizer = TransactionCategoriser()
        self.prefix = 'lloyds'
        self.currency = "GBP"
        self.pages = None
