from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FloatField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Optional, NumberRange

class PartForm(FlaskForm):
    stock_id = StringField('Stock ID', validators=[DataRequired()])
    part_name = StringField('Part Name', validators=[DataRequired()])
    category = SelectField('Category', choices=[
        ('Engine', 'Engine'), ('Gearbox', 'Gearbox'), 
        ('Body Panel', 'Body Panel'), ('Electronics', 'Electronics'),
        ('Interior', 'Interior'), ('Wheels', 'Wheels'),
        ('Lighting', 'Lighting'), ('Suspension', 'Suspension'),
        ('Brakes', 'Brakes'), ('Exhaust', 'Exhaust'), ('Other', 'Other')
    ], validators=[DataRequired()])
    part_type = StringField('Part Type', validators=[Optional()])
    make = StringField('Make', validators=[Optional()])
    model = StringField('Model', validators=[Optional()])
    generation = StringField('Generation', validators=[Optional()])
    oem_number = StringField('OEM Number', validators=[Optional()])
    engine_code = StringField('Engine Code', validators=[Optional()])
    condition = SelectField('Condition', choices=[
        ('Good', 'Good'), ('Tested', 'Tested'), ('New', 'New'),
        ('Refurbished', 'Refurbished'), ('As Is', 'As Is')
    ], validators=[Optional()])
    price = FloatField('Price (£)', validators=[Optional(), NumberRange(min=0)])
    stock_status = SelectField('Stock Status', choices=[
        ('Available', 'Available'), ('Reserved', 'Reserved'), ('Sold', 'Sold')
    ], validators=[Optional()])
    location = StringField('Location', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
