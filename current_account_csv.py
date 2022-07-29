from beancount.ingest.importers import csv
from beancount.ingest.importers.mixins import filing
import os
# os.sys.path.append('..')
from categorisers.lloyds_current import TransactionCategoriser


class Importer(csv.Importer):

    config = {
              csv.Col.DATE:          'Transaction Date',
              csv.Col.NARRATION:     'Transaction Description',
              csv.Col.TAG:           'Transaction Type',
              csv.Col.AMOUNT_DEBIT:  'Debit Amount',
              csv.Col.AMOUNT_CREDIT: 'Credit Amount',
              csv.Col.BALANCE:       'Balance',
    }

    def __init__(self, account):#, account_number, sort_code):
        # self.account_number = account_number
        # self.sort_code      = sort_code
        csv.Importer.__init__(self,
            config = self.config,
            account = account,
            currency = "GBP",
            regexps =  [
                '^Transaction Date,Transaction Type,Sort Code,Account Number,Transaction Description,Debit Amount,Credit Amount,Balance',
            ],
            dateutil_kwds =  { "yearfirst": False, "dayfirst": True },
            categorizer = TransactionCategoriser(),
            institution = "lloyds",
	)

    def file_name(self, file):
        return (
            super()
            .file_name(file)
            .replace(
                os.path.basename(file.name),
                "statement.csv"
            )
        )

