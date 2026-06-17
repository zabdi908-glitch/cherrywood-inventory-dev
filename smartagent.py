import os
import cv2
import pytesseract
import requests
import json
import re
from PIL import Image
import io
import numpy as np
from datetime import datetime

class SmartVehicleAgent:
    def __init__(self):
        self.car_makes = {
            'audi': ['a3', 'a4', 'a5', 'a6', 'q3', 'q5', 'q7', 'tt', 'r8'],
            'volkswagen': ['golf', 'polo', 'passat', 'tiguan', 'touran', 'transporter'],
            'seat': ['ibiza', 'leon', 'arona', 'ateca', 'tarraco'],
            'skoda': ['octavia', 'fabia', 'superb', 'kodiaq', 'karoa'],
            'bmw': ['1 series', '3 series', '5 series', 'x1', 'x3', 'x5'],
            'mercedes': ['a class', 'c class', 'e class', 'gla', 'glc', 'gle'],
            'ford': ['fiesta', 'focus', 'mondeo', 'kuga', 'transit'],
            'vauxhall': ['astra', 'corsa', 'insignia', 'mokka', 'vivaro'],
            'toyota': ['yaris', 'corolla', 'rav4', 'hilux', 'land cruiser'],
            'hyundai': ['i10', 'i20', 'i30', 'tucson', 'santa fe']
        }
    
    def analyze_vehicle_image(self, image_url):
        """Main function to analyze vehicle from image"""
        try:
            # Download image
            image = self.download_image(image_url)
            
            if image is None:
                return {'success': False, 'error': 'Could not download image'}
            
            # Extract license plate
            plate_text = self.extract_license_plate(image)
            
            # Identify vehicle details
            vehicle_details = self.identify_vehicle(image, plate_text)
            
            # Generate auto-description
            description = self.generate_description(vehicle_details)
            
            # Suggest parts
            parts = self.suggest_parts(vehicle_details)
            
            return {
                'success': True,
                'vehicle': vehicle_details,
                'plate': plate_text,
                'description': description,
                'suggested_parts': parts,
                'status': 'Breaking'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def download_image(self, image_url):
        """Download image from URL"""
        try:
            response = requests.get(image_url, timeout=10)
            img = Image.open(io.BytesIO(response.content))
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        except:
            return None
    
    def extract_license_plate(self, image):
        """Extract license plate from image using OCR"""
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply OCR
            text = pytesseract.image_to_string(gray, config='--psm 8')
            
            # Clean up - look for UK plate format
            patterns = [
                r'[A-Z]{2}[0-9]{2}\s?[A-Z]{3}',
                r'[A-Z]{2}[0-9]{2}\s?[A-Z]{2}',
                r'[A-Z][0-9]{3}\s?[A-Z]{3}'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text.upper())
                if match:
                    return match.group().replace(' ', '')
            
            return 'UNKNOWN'
        except:
            return 'UNKNOWN'
    
    def identify_vehicle(self, image, plate):
        """Identify vehicle from image"""
        # This is simplified - in production you'd use AI models
        # For now, try to extract from plate if possible
        vehicle_details = {
            'make': 'Unknown',
            'model': 'Unknown',
            'year': self.extract_year_from_plate(plate),
            'fuel': 'Diesel',
            'transmission': 'Manual',
            'engine': 'Unknown',
            'mileage': 'Unknown'
        }
        
        return vehicle_details
    
    def extract_year_from_plate(self, plate):
        """Extract year from UK registration plate"""
        try:
            if len(plate) >= 4:
                year_code = plate[2:4]
                if year_code.isdigit():
                    year = int(year_code)
                    if year >= 50:
                        return f"20{year - 50}"
                    else:
                        return f"20{year}"
        except:
            pass
        return '2015'
    
    def generate_description(self, vehicle):
        """Generate auto-description"""
        make = vehicle.get('make', 'Vehicle')
        model = vehicle.get('model', '')
        year = vehicle.get('year', '')
        
        description = f"Clean {make} {model} {year} being broken for parts. "
        description += f"This {make} {model} has been fully tested and all components are available. "
        description += "Our team has inspected every part to ensure quality. "
        description += f"Contact us for specific {make} {model} parts availability."
        
        return description
    
    def suggest_parts(self, vehicle):
        """Suggest available parts based on vehicle"""
        common_parts = [
            'Engine', 'Gearbox', 'Turbo', 'Injectors',
            'Alternator', 'Starter Motor', 'ECU',
            'Headlights', 'Taillights', 'Bumper',
            'Wings', 'Doors', 'Tailgate',
            'Alloy Wheels', 'Seats', 'Steering Wheel'
        ]
        
        if vehicle.get('fuel', '').lower() == 'diesel':
            common_parts.extend(['DPF', 'EGR Valve', 'Diesel Pump'])
        
        return ', '.join(common_parts)
    
    def format_for_database(self, analysis_result):
        """Format analysis result for database insertion"""
        if not analysis_result['success']:
            return None
        
        vehicle = analysis_result['vehicle']
        
        return {
            'title': f"{vehicle.get('year', '')} {vehicle.get('make', '')} {vehicle.get('model', '')} Breaker - All Parts Available",
            'make': vehicle.get('make', 'Unknown'),
            'model': vehicle.get('model', 'Unknown'),
            'year': vehicle.get('year', '2015'),
            'reg': analysis_result.get('plate', 'UNKNOWN'),
            'engine': vehicle.get('engine', 'Unknown'),
            'fuel': vehicle.get('fuel', 'Diesel'),
            'transmission': vehicle.get('transmission', 'Manual'),
            'mileage': vehicle.get('mileage', 'Unknown'),
            'status': analysis_result.get('status', 'Breaking'),
            'image_url': '',
            'parts_available': analysis_result.get('suggested_parts', ''),
            'description': analysis_result.get('description', '')
        }

# Initialize agent
smart_agent = SmartVehicleAgent()
