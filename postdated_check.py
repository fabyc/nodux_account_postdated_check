# -*- coding: utf-8 -*-
#This file is part of the nodux_account_postdated_check module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from decimal import Decimal
from trytond.model import ModelSingleton, ModelView, ModelSQL, fields
from trytond.transaction import Transaction
from trytond.pyson import Eval, In
from trytond.pool import Pool
from trytond.report import Report
import pytz
from datetime import datetime,timedelta
import time

conversor = None
try:
    from numword import numword_es
    conversor = numword_es.NumWordES()
except:
    print("Warning: Does not possible import numword module!")
    print("Please install it...!")


__all__ = [ 'PostDatedCheckSequence', 'AccountPostDateCheck', 'AccountPostDatedCheckLine']

_STATES = {
    'readonly': In(Eval('state'), ['posted']),
}

class PostDatedCheckSequence(ModelSingleton, ModelSQL, ModelView):
    'Post Dated Check Sequence'
    __name__ = 'account.postdated.sequence'

    postdated_sequence = fields.Property(fields.Many2One('ir.sequence',
        'Post dated check sequence', required=True,
        domain=[('code', '=', 'account.postdated')]))

class AccountPostDateCheck(ModelSQL, ModelView):
    'Account Post Date Check'
    __name__ = 'account.postdated'
    _rec_name = 'number'

    number = fields.Char('Number', readonly=True, help="Post dated check number")
    party = fields.Many2One('party.party', 'Party', required=True, readonly = True)
    post_check_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ], 'Type', select=True, required=True, states=_STATES)
    date = fields.Date('Date', required=True, states=_STATES)
    journal = fields.Many2One('account.journal', 'Journal', required=True,
        states=_STATES)
    currency = fields.Many2One('currency.currency', 'Currency', states=_STATES)
    company = fields.Many2One('company.company', 'Company', states=_STATES)
    lines = fields.One2Many('account.postdated.line', 'postdated', 'Lines',
        states=_STATES)
    comment = fields.Char('Comment', states=_STATES)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ], 'State', select=True, readonly=True)
    move = fields.Many2One('account.move', 'Move', readonly=True)

    @classmethod
    def __setup__(cls):
        super(AccountPostDateCheck, cls).__setup__()
        cls._error_messages.update({
            'delete_postdated': 'You can not delete a postdated check that is posted!',
        })
        cls._buttons.update({
                'post': {
                    'invisible': Eval('state') == 'posted',
                    },
                })
        cls._order.insert(0, ('date', 'DESC'))
        cls._order.insert(1, ('number', 'DESC'))


    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_currency():
        Company = Pool().get('company.company')
        company_id = Transaction().context.get('company')
        if company_id:
            return Company(company_id).currency.id

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_journal():
        pool = Pool()
        Journal = pool.get('account.journal')
        journal = Journal.search([('type','=', 'expense')])
        journal_r = Journal.search([('type', '=', 'revenue')])
        post_check_type_id = Transaction().context.get('post_check_type')
        if post_check_type_id == 'receipt':
            for j in journal_r:
                return j.id

        if post_check_type_id == 'payment':
            for j in journal:
                return j.id

    def set_number(self):
        Sequence = Pool().get('ir.sequence')
        AccountPostDatedSequence = Pool().get('account.postdated.sequence')
        sequence = AccountPostDatedSequence(1)
        self.write([self], {'number': Sequence.get_id(
            sequence.postdated_sequence.id)})

    def prepare_lines(self):
        pool = Pool()
        Period = pool.get('account.period')
        Move = pool.get('account.move')

        move_lines = []
        line_move_ids = []
        move, = Move.create([{
            'period': Period.find(self.company.id, date=self.date),
            'journal': self.journal.id,
            'date': self.date,
            'origin': str(self),
        }])
        self.write([self], {
                'move': move.id,
                })

        for line in self.lines:
            if line.account_new:
                account_new = line.account_new
            else:
                self.raise_user_error("No ha ingresado la cuenta de Bancos")

            if self.post_check_type == 'receipt':
                debit = Decimal('0.00')
                credit = line.amount
                total = line.amount
            else:
                debit = line.amount
                credit = Decimal('0.00')
                total = line.amount

            move_lines.append({
                'description': self.number,
                'debit': debit,
                'credit': credit,
                'account': line.account.id,
                'move': move.id,
                'journal': self.journal.id,
                'period': Period.find(self.company.id, date=self.date),
                })

            if self.post_check_type == 'receipt':
                debit = total
                credit = Decimal(0.0)
            else:
                debit = Decimal(0.0)
                credit = total

            move_lines.append({
                'description': self.number,
                'debit': debit,
                'credit': credit,
                'account': line.account_new.id,
                'move': move.id,
                'journal': self.journal.id,
                'period': Period.find(self.company.id, date=self.date),
                'date': self.date,
            })
        return move_lines

    def deposit(self, move_lines):
        pool = Pool()
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        created_lines = MoveLine.create(move_lines)
        Move.post([self.move])
        Voucher = pool.get('account.voucher')

        reconcile_lines = []

        for line in self.lines:
            voucher = Voucher.search([('number', '=', line.name)])
            for v in voucher:
                move = v.move
            line_r = MoveLine.search([('account', '=', line.account.id), ('move', '=', move.id)])

            for line in line_r:
                reconcile_lines.append(line)
            for move_line in created_lines:
                if move_line.account.id == line.account.id:
                    reconcile_lines.append(move_line)
            MoveLine.reconcile(reconcile_lines)

        return True

    @classmethod
    def delete(cls, postdateds):
        if not postdateds:
            return True
        for postdated in postdateds:
            if postdated.state == 'posted':
                cls.raise_user_error('delete_postdated')
        return super(AccountPostDateCheck, cls).delete(postdateds)

    @classmethod
    @ModelView.button
    def post(cls, postdateds):
        for postdated in postdateds:
            postdated.set_number()
            move_lines = postdated.prepare_lines()
            postdated.deposit(move_lines)
        cls.write(postdateds, {'state': 'posted'})

class AccountPostDatedCheckLine(ModelSQL, ModelView):
    'Account Post Dated Check Line'
    __name__ = 'account.postdated.line'

    postdated = fields.Many2One('account.postdated', 'Postdated check')
    name = fields.Char('Reference')
    account = fields.Many2One('account.account', 'Account')
    amount = fields.Numeric('Amount', digits=(16, 2))
    move_line = fields.Many2One('account.move.line', 'Move Line', readonly=True)
    date = fields.Date('Date')
    account_new = fields.Many2One('account.account', 'Account bank')
    number = fields.Char('Deposit number')
