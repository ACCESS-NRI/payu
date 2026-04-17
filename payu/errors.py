
# TODO double check which custom exceptions would be useful
# from a user point of view. Is it useful to have a PayuError class
# as a base class or do we not need it.

class PayuError(Exception):
    '''Base class for all payu exceptions.'''
    exit_code = 1

class PayuBranchError(PayuError):
    '''Custom Exception for payu branch operations'''
    exit_code = 2