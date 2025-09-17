# Event RSVP System

## Overview

This is a Flask-based event RSVP management system that allows guests to confirm attendance, provide dietary requirements, and select seating arrangements. The application features a complete guest management workflow including RSVP forms, seating charts, and confirmation pages. It uses a file-based JSON database for data persistence and includes deadline management for seat changes.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Template Engine**: Jinja2 templates with Flask for server-side rendering
- **Base Template Pattern**: Uses template inheritance with `base.html` as the foundation
- **Responsive Design**: CSS-based responsive layout with grid systems
- **Client-Side Logic**: Vanilla JavaScript for form interactions and seat selection

### Backend Architecture
- **Framework**: Flask web application framework
- **Route Structure**: RESTful routes for RSVP workflow (`/`, `/rsvp`, `/seating`)
- **Session Management**: Flask sessions with secret key configuration
- **Data Validation**: Server-side form validation and deadline enforcement

### Data Storage
- **Database Type**: File-based JSON storage (`event_data.json`)
- **Data Structure**: Nested JSON with separate collections for RSVPs and seating arrangements
- **Schema Design**: 
  - RSVPs indexed by email address with guest details, dietary requirements, and timestamps
  - Seating organized by table with 10-seat capacity per table (10 tables total)
- **Persistence**: Manual file I/O operations with load/save functions

### Key Features
- **RSVP Management**: Binary attendance confirmation with detailed guest information collection
- **Guest List Handling**: Support for bringing additional guests with name collection
- **Dietary Accommodations**: Dietary requirements and food allergy tracking
- **Seating System**: Interactive seating chart with availability visualization
- **Deadline Management**: Configurable deadline for seat changes (currently set to October 1, 2025)
- **Form Validation**: Both client-side and server-side validation for data integrity

### Security Considerations
- Basic session management with configurable secret key
- Form data sanitization through Flask's request handling
- No authentication system implemented (open RSVP system)

## External Dependencies

### Core Framework
- **Flask**: Python web framework for routing, templating, and request handling
- **Jinja2**: Template engine (included with Flask)

### Data Handling
- **JSON**: Native Python JSON library for data serialization
- **OS/File System**: Direct file operations for database persistence

### Frontend Libraries
- **Vanilla JavaScript**: No external JavaScript frameworks
- **CSS3**: Custom styling without external CSS frameworks

### System Dependencies
- **Python 3.x**: Runtime environment
- **File System Access**: Required for JSON database operations

Note: The application currently uses file-based storage but is structured in a way that could easily migrate to a relational database system like PostgreSQL with minimal code changes to the data access layer.