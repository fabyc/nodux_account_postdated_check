#This file is part of the nodux_account_postdated_check module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.

from trytond.pool import Pool
from .postdated_check import *
from .move import*

def register():
    Pool.register(
        PostDatedCheckSequence,
        AccountPostDateCheck,
        AccountPostDatedCheckLine,
        Move,
        ProtestedCheckStart,
        module='nodux_account_postdated_check', type_='model')
    Pool.register(
        ProtestedCheck,
        module='nodux_account_postdated_check', type_='wizard')
    Pool.register(
        PrintCheck,
        module='nodux_account_postdated_check', type_='report')
