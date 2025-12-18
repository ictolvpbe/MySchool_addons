# -*- coding: utf-8 -*-
"""
Informat DTOs (Data Transfer Objects)
=====================================

These classes represent the JSON structures received from Informat API.
They help with type safety and IDE auto-completion when working with
imported data.

Equivalent to Java classes in edu.myschool.services.syncsap.informat package:
- Registration
- Students
- Employee
- Assignments
- Relations
- InschrKlassen
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Dict, Any
import json


@dataclass
class InschrKlassen:
    """
    Class registration information.
    Represents a student's class enrollment period.
    """
    klas: str = ''
    groep_type: int = 0
    klas_code: str = ''
    einddatum: Optional[str] = None
    begindatum: Optional[str] = None
    klasnummer: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InschrKlassen':
        return cls(
            klas=data.get('klas', ''),
            groep_type=data.get('groepType', 0),
            klas_code=data.get('klasCode', ''),
            einddatum=data.get('einddatum'),
            begindatum=data.get('begindatum'),
            klasnummer=data.get('klasnummer', 0)
        )


@dataclass
class Relations:
    """
    Student relation information (parents, guardians, etc.).
    """
    relatie_id: str = ''
    relatie_type: str = ''
    first_name: str = ''
    last_name: str = ''
    phone: str = ''
    mobile: str = ''
    email: str = ''
    is_contact_person: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Relations':
        return cls(
            relatie_id=data.get('relatieId', ''),
            relatie_type=data.get('relatieType', ''),
            first_name=data.get('firstName', data.get('voornaam', '')),
            last_name=data.get('lastName', data.get('naam', '')),
            phone=data.get('phone', data.get('telefoon', '')),
            mobile=data.get('mobile', data.get('gsm', '')),
            email=data.get('email', ''),
            is_contact_person=data.get('isContactPerson', data.get('isContactpersoon', False))
        )


@dataclass
class Address:
    """
    Address information.
    """
    address_id: str = ''
    street: str = ''
    house_number: str = ''
    box: str = ''
    postal_code: str = ''
    city: str = ''
    country: str = ''
    address_type: str = ''
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Address':
        return cls(
            address_id=data.get('addressId', data.get('adresId', '')),
            street=data.get('street', data.get('straat', '')),
            house_number=data.get('houseNumber', data.get('huisnummer', '')),
            box=data.get('box', data.get('bus', '')),
            postal_code=data.get('postalCode', data.get('postcode', '')),
            city=data.get('city', data.get('gemeente', '')),
            country=data.get('country', data.get('land', '')),
            address_type=data.get('addressType', data.get('adresType', ''))
        )


@dataclass
class Registration:
    """
    Student registration data.
    Contains information about a student's enrollment.
    """
    persoon_id: str = ''
    instelnr: str = ''
    status: int = 0
    inschr_klassen: List[InschrKlassen] = field(default_factory=list)
    reg_start_date: Optional[str] = None
    reg_end_date: Optional[str] = None
    reg_group_code: str = ''
    reg_inst_nr: str = ''
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Registration':
        inschr_klassen = [
            InschrKlassen.from_dict(k) 
            for k in data.get('inschrklassen', data.get('inschrKlassen', []))
        ]
        return cls(
            persoon_id=data.get('persoonId', ''),
            instelnr=data.get('instelnr', ''),
            status=data.get('status', 0),
            inschr_klassen=inschr_klassen,
            reg_start_date=data.get('regStartDate'),
            reg_end_date=data.get('regEndDate'),
            reg_group_code=data.get('regGroupCode', ''),
            reg_inst_nr=data.get('regInstNr', '')
        )
    
    def get_active_class(self) -> Optional[InschrKlassen]:
        """Get the currently active class (where einddatum is None)."""
        for klas in self.inschr_klassen:
            if klas.einddatum is None:
                return klas
        return None


@dataclass
class Students:
    """
    Student details data.
    Contains personal information about a student.
    """
    persoon_id: str = ''
    first_name: str = ''
    last_name: str = ''
    birth_date: Optional[str] = None
    gender: str = ''
    nationality: str = ''
    national_number: str = ''
    relaties: List[Relations] = field(default_factory=list)
    addresses: List[Address] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    phone_numbers: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Students':
        relaties = [Relations.from_dict(r) for r in data.get('relaties', [])]
        addresses = [Address.from_dict(a) for a in data.get('adressen', data.get('addresses', []))]
        
        return cls(
            persoon_id=data.get('persoonId', ''),
            first_name=data.get('firstName', data.get('voornaam', '')),
            last_name=data.get('lastName', data.get('naam', '')),
            birth_date=data.get('birthDate', data.get('geboortedatum')),
            gender=data.get('gender', data.get('geslacht', '')),
            nationality=data.get('nationality', data.get('nationaliteit', '')),
            national_number=data.get('nationalNumber', data.get('rijksregisternummer', '')),
            relaties=relaties,
            addresses=addresses,
            emails=data.get('emails', []),
            phone_numbers=data.get('phoneNumbers', data.get('telefoons', []))
        )


@dataclass
class Employee:
    """
    Employee data from Informat.
    """
    person_id: str = ''
    first_name: str = ''
    last_name: str = ''
    birth_date: Optional[str] = None
    gender: str = ''
    email: str = ''
    hoofd_ambt: str = ''
    hoofd_ambt_code: str = ''
    is_active: bool = True
    is_overleden: bool = False
    pension_date: Optional[str] = None
    inst_nr: str = ''
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Employee':
        return cls(
            person_id=data.get('personId', ''),
            first_name=data.get('firstName', data.get('voornaam', '')),
            last_name=data.get('lastName', data.get('naam', '')),
            birth_date=data.get('birthDate', data.get('geboortedatum')),
            gender=data.get('gender', data.get('geslacht', '')),
            email=data.get('email', ''),
            hoofd_ambt=data.get('hoofdAmbt', ''),
            hoofd_ambt_code=data.get('hoofdAmbtCode', ''),
            is_active=data.get('isActive', True),
            is_overleden=data.get('isOverleden', False),
            pension_date=data.get('pensionDate', data.get('pensioenDatum')),
            inst_nr=data.get('instNr', '')
        )


@dataclass
class Assignments:
    """
    Employee assignment data.
    Represents an employee's position/role assignment.
    """
    assignment_id: str = ''
    person_id: str = ''
    ambt: str = ''
    ambt_code: str = ''
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    percentage: float = 0.0
    is_hoofd_opdracht: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Assignments':
        return cls(
            assignment_id=data.get('assignmentId', data.get('id', '')),
            person_id=data.get('personId', ''),
            ambt=data.get('ambt', ''),
            ambt_code=data.get('ambtCode', ''),
            start_date=data.get('startDate', data.get('startDatum')),
            end_date=data.get('endDate', data.get('eindDatum')),
            percentage=data.get('percentage', 0.0),
            is_hoofd_opdracht=data.get('isHoofdOpdracht', False)
        )


@dataclass
class PersonJSON:
    """
    Person data structure for BeTask JSON.
    Used when creating BeTasks with person data.
    """
    sap_person_uuid: str = ''
    first_name: str = ''
    last_name: str = ''
    birth_date: Optional[str] = None
    gender: str = ''
    person_type: str = ''
    reg_start_date: Optional[str] = None
    reg_end_date: Optional[str] = None
    reg_group_code: str = ''
    reg_inst_nr: str = ''
    inschr_klassen: List[InschrKlassen] = field(default_factory=list)
    
    @classmethod
    def from_registration_and_student(cls, registration: Registration, student: Optional[Students] = None) -> 'PersonJSON':
        """Create PersonJSON from registration and optional student data."""
        person = cls(
            sap_person_uuid=registration.persoon_id,
            reg_start_date=registration.reg_start_date,
            reg_end_date=registration.reg_end_date,
            reg_group_code=registration.reg_group_code,
            reg_inst_nr=registration.reg_inst_nr or registration.instelnr,
            inschr_klassen=registration.inschr_klassen
        )
        
        if student:
            person.first_name = student.first_name
            person.last_name = student.last_name
            person.birth_date = student.birth_date
            person.gender = student.gender
            person.person_type = 'STUDENT'
        
        # Get active class info
        active_class = registration.get_active_class()
        if active_class:
            person.reg_group_code = active_class.klas_code
            person.reg_start_date = active_class.begindatum
        
        return person
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'sapPersonUUID': self.sap_person_uuid,
            'firstName': self.first_name,
            'lastName': self.last_name,
            'birthDate': self.birth_date,
            'gender': self.gender,
            'personType': self.person_type,
            'regStartDate': self.reg_start_date,
            'regEndDate': self.reg_end_date,
            'regGroupCode': self.reg_group_code,
            'regInstNr': self.reg_inst_nr,
            'inschrKlassen': [
                {
                    'klas': k.klas,
                    'groepType': k.groep_type,
                    'klasCode': k.klas_code,
                    'einddatum': k.einddatum,
                    'begindatum': k.begindatum,
                    'klasnummer': k.klasnummer
                }
                for k in self.inschr_klassen
            ]
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


# Helper functions for JSON parsing
def parse_registration(json_str: str) -> Registration:
    """Parse JSON string to Registration object."""
    data = json.loads(json_str)
    return Registration.from_dict(data)


def parse_student(json_str: str) -> Students:
    """Parse JSON string to Students object."""
    data = json.loads(json_str)
    return Students.from_dict(data)


def parse_employee(json_str: str) -> Employee:
    """Parse JSON string to Employee object."""
    data = json.loads(json_str)
    return Employee.from_dict(data)


def parse_assignment(json_str: str) -> Assignments:
    """Parse JSON string to Assignments object."""
    data = json.loads(json_str)
    return Assignments.from_dict(data)
