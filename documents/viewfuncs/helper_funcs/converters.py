from decimal import Decimal

class DecimalConverter:
    regex = r'\d+\.\d+'
    def to_python(self, value):
        return Decimal(value)
    
    def to_url(self, value):
        return str(value)