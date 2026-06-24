from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FloatField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Optional, NumberRange, Length, Regexp

class PartForm(FlaskForm):
    # ✅ Required fields with validation
    stock_id = StringField('Stock ID', validators=[
        DataRequired(message="Stock ID is required"),
        Length(min=2, max=20, message="Stock ID must be between 2 and 20 characters")
    ])
    
    part_name = StringField('Part Name', validators=[
        DataRequired(message="Part name is required"),
        Length(min=3, max=100, message="Part name must be between 3 and 100 characters")
    ])
    
    category = SelectField('Category', choices=[
        ('Engine', 'Engine'), ('Gearbox', 'Gearbox'), 
        ('Body Panel', 'Body Panel'), ('Electronics', 'Electronics'),
        ('Interior', 'Interior'), ('Wheels', 'Wheels'),
        ('Lighting', 'Lighting'), ('Suspension', 'Suspension'),
        ('Brakes', 'Brakes'), ('Exhaust', 'Exhaust'), ('Other', 'Other')
    ], validators=[DataRequired(message="Please select a category")])
    
    part_type = StringField('Part Type', validators=[Optional(), Length(max=50)])
    make = StringField('Make', validators=[Optional(), Length(max=50)])
    model = StringField('Model', validators=[Optional(), Length(max=50)])
    generation = StringField('Generation', validators=[Optional(), Length(max=20)])
    
    # ✅ OEM number with optional format validation
    oem_number = StringField('OEM Number', validators=[
        Optional(),
        Length(max=30, message="OEM number must be less than 30 characters")
    ])
    
    engine_code = StringField('Engine Code', validators=[Optional(), Length(max=20)])
    
    condition = SelectField('Condition', choices=[
        ('Good', 'Good'), ('Tested', 'Tested'), ('New', 'New'),
        ('Refurbished', 'Refurbished'), ('As Is', 'As Is')
    ], validators=[Optional()])
    
    # ✅ Price validation (must be a positive number)
    price = FloatField('Price (£)', validators=[
        Optional(),
        NumberRange(min=0, max=99999, message="Price must be between £0 and £99,999")
    ])
    
    stock_status = SelectField('Stock Status', choices=[
        ('Available', 'Available'), ('Reserved', 'Reserved'), ('Sold', 'Sold')
    ], validators=[Optional()])
    
    location = StringField('Location', validators=[Optional(), Length(max=50)])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=500)])
