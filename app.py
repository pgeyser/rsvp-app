from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from datetime import datetime, date, timedelta
import csv
import io
import json
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
# Re-check template files on each render so edits show up without a restart
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Simple file-based database
DATABASE_FILE = 'data/event_data.json'

# Deadline for RSVPs and seat changes (guests only — organisers logged in to
# /admin can still book and move people after this date)
SEAT_CHANGE_DEADLINE = date(2026, 10, 2)

# Password for the /admin page (override with the ADMIN_PASSWORD env var)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'masquerade2026')

# Casino Royale table names, shown alongside the table number
TABLE_NAMES = {
    'table_1': 'Casino Royale',
    'table_2': 'Goldfinger',
    'table_3': 'GoldenEye',
    'table_4': 'Skyfall',
    'table_5': 'Dr. No',
    'table_6': 'Thunderball',
    'table_7': 'Moonraker',
    'table_8': 'Spectre',
    'table_9': 'Licence to Kill',
    'table_10': 'Diamonds Are Forever',
    'table_11': 'From Russia with Love',
    'table_12': 'You Only Live Twice',
    'table_13': 'On Her Majesty\'s Secret Service',
    'table_14': 'The Spy Who Loved Me',
    'table_15': 'Live and Let Die',
}

# Every table seats ten unless listed here
DEFAULT_TABLE_SIZE = 10
TABLE_SIZES = {
    'table_7': 11,  # Moonraker
}


def table_size(table):
    return TABLE_SIZES.get(table, DEFAULT_TABLE_SIZE)


def empty_table(table):
    return [None] * table_size(table)


NUMBER_WORDS = ['One', 'Two', 'Three', 'Four', 'Five',
                'Six', 'Seven', 'Eight', 'Nine', 'Ten',
                'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen']

# Event start, used for the landing page countdown (South Africa has no DST)
EVENT_START = datetime(2026, 10, 30, 16, 30, 0)


def table_display(table):
    """Human name like 'Table Two — Goldfinger', matching the landing page."""
    try:
        base = f"Table {NUMBER_WORDS[int(table.split('_')[1]) - 1]}"
    except (AttributeError, IndexError, ValueError):
        base = table.replace('_', ' ').title() if table else 'Unknown Table'
    name = TABLE_NAMES.get(table)
    return f'{base} — {name}' if name else base


def norm_email(email):
    return email.strip().lower() if email else email


def normalise_seats(data):
    """Make sure every table exists and has exactly its number of seats.

    The data file on disk may predate a table being added or resized; pad
    with empty seats, and only ever trim seats that are empty.
    """
    data.setdefault('rsvps', {})
    data.setdefault('cancel', {})
    seats = data.setdefault('seats', {})
    for table in TABLE_NAMES:
        occupants = list(seats.get(table) or [])
        size = table_size(table)
        if len(occupants) < size:
            occupants.extend([None] * (size - len(occupants)))
        while len(occupants) > size and occupants[-1] is None:
            occupants.pop()
        seats[table] = occupants
    return data


def load_db():
    """Load database from file"""
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            data = json.load(f)
    else:
        # Initialize default structure
        data = {'rsvps': {}, 'cancel': {}, 'seats': {}}
    return normalise_seats(data)


def seat_changes_closed():
    """True once the deadline has passed — unless an organiser is logged in."""
    return date.today() > SEAT_CHANGE_DEADLINE and not session.get('is_admin')


def save_db(data):
    """Save database to file"""
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def static_image(name):
    """Static-relative path for the first matching extension on disk, else None."""
    for ext in ('png', 'jpg', 'jpeg', 'webp'):
        filename = f'{name}.{ext}'
        if os.path.exists(os.path.join(app.static_folder, 'images', filename)):
            return f'images/{filename}'
    return None


def countdown_parts():
    """Initial countdown values so the page paints correctly before JS runs."""
    remaining = max(EVENT_START - datetime.now(), timedelta(0))
    hours, rem = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return {'days': f'{remaining.days:02d}', 'hours': f'{hours:02d}',
            'minutes': f'{minutes:02d}', 'seconds': f'{seconds:02d}'}


@app.route('/')
def index():
    # Feedback strips for round-trips from other pages
    notice = None
    if request.args.get('cancelled'):
        notice = "Your RSVP has been cancelled and your seats are free again. We're sorry you can't make it."
    elif request.args.get('unknown'):
        notice = "We couldn't find an RSVP under that email. If you haven't replied yet, the invitation below is yours."

    data = load_db()
    seats = data['seats']

    tables = []
    for i, key in enumerate(TABLE_NAMES, start=1):
        occupants = seats[key]
        guests = []
        labels = []
        for n, occ in enumerate(occupants):
            if occ:
                name = f"{occ.get('full_name', '')} {occ.get('surname', '')}".strip() or 'Reserved'
                guests.append({
                    'name': name,
                    'partner': str(occ.get('email', '')).endswith('_guest'),
                })
                labels.append(name)
            else:
                labels.append(f'Seat {n + 1} — available')
        tables.append({
            'key': key,
            'number': f'Table {NUMBER_WORDS[i - 1]}',
            'name': TABLE_NAMES[key],
            'occupied': [occ is not None for occ in occupants],
            'labels': labels,
            'guests': guests,
            'size': len(occupants),
            'free': sum(1 for occ in occupants if occ is None),
        })

    return render_template('index.html',
                           tables=tables,
                           notice=notice,
                           total_free=sum(t['free'] for t in tables),
                           active_key=next((t['key'] for t in tables if t['free'] > 0), 'table_1'),
                           countdown=countdown_parts(),
                           hero_image=static_image('hero-crowd'),
                           banner_image=static_image('banner-room'),
                           look_images={slot: static_image(f'look-{slot}')
                                        for slot in ('jacket', 'gown', 'diamonds', 'cuff')})


@app.route('/rsvp', methods=['GET', 'POST'])
def rsvp():
    if request.method == 'POST':
        # Get form data
        attending = request.form.get('attending')

        # Declines get recorded too, so the organisers know who replied
        if attending == 'no':
            full_name = (request.form.get('decline_name') or '').strip()
            email = norm_email(request.form.get('decline_email'))

            if not full_name or not email:
                return render_template('rsvp_form.html', form=request.form,
                                       decline_error='Please leave your name and email so we know who sent their regrets.')

            db = load_db()
            db['cancel'][email] = {
                'full_name': full_name,
                'email': email,
                'submitted_at': datetime.now().isoformat()
            }
            # If they had RSVP'd before, free their seats
            for t in db['seats']:
                for i, occupant in enumerate(db['seats'][t]):
                    if occupant and occupant.get('email') in (email, email + '_guest'):
                        db['seats'][t][i] = None
            save_db(db)

            return render_template('thank_you.html', mode='declined')

        # Extract form data for attending guests
        full_name = request.form.get('full_name')
        surname = request.form.get('surname')
        email = norm_email(request.form.get('email'))
        cellphone = request.form.get('cellphone')
        bringing_guest = request.form.get('bringing_guest')
        guest_list = request.form.get('guest_list', '')
        dietary_requirements = request.form.get('dietary_requirements')
        food_allergies = request.form.get('food_allergies', '')

        # Validate required fields; hand the typed values back so nothing is lost
        if not all([full_name, surname, email, cellphone, dietary_requirements]):
            table = request.form.get('table')
            valid_table = table if table in TABLE_NAMES else None
            return render_template('rsvp_form.html', form=request.form,
                                   table=valid_table,
                                   table_label=table_display(valid_table) if valid_table else None,
                                   error="Please fill in all required fields")

        # Store RSVP data
        rsvp_data = {
            'full_name': full_name,
            'surname': surname,
            'email': email,
            'cellphone': cellphone,
            'bringing_guest': bringing_guest,
            'guest_list': guest_list.strip() if guest_list else '',
            'dietary_requirements': dietary_requirements,
            'food_allergies': food_allergies,
            'submitted_at': datetime.now().isoformat()
        }

        # Update database
        data = load_db()
        data['rsvps'][email] = rsvp_data
        save_db(data)

        # Redirect to the seating chart, landing on the table they picked
        table = request.form.get('table')
        target = url_for('seating_chart', email=email)
        if table in TABLE_NAMES:
            target += f'#{table}'
        return redirect(target)

    # "Sit with me" share links prefill the invitee's name (?name=Full+Name);
    # "Claim a seat" links carry the chosen table (?table=table_N)
    invited = request.args.get('name', '').strip()
    first, _, last = invited.rpartition(' ') if ' ' in invited else (invited, '', '')
    table = request.args.get('table')
    return render_template('rsvp_form.html',
                           form={'full_name': first, 'surname': last},
                           table=table if table in TABLE_NAMES else None,
                           table_label=table_display(table) if table in TABLE_NAMES else None)


@app.route('/cancel', methods=['GET', 'POST'])
def cancel():
    if request.method == 'POST':
        # Extract form data
        full_name = request.form.get('full_name')
        email = norm_email(request.form.get('email'))

        # Validate required fields
        if not all([full_name, email]):
            return render_template('thank_you.html', mode='cancel',
                                   error="Please fill in all required fields")

        # Store cancellation
        cancel_data = {
            'full_name': full_name,
            'email': email,
            'submitted_at': datetime.now().isoformat()
        }

        db = load_db()
        db['cancel'][email] = cancel_data

        # Free any seats held by the user or their guest
        seats = db['seats']
        for t in seats:
            for i, occupant in enumerate(seats[t]):
                if occupant and occupant.get('email') in (email, email + '_guest'):
                    seats[t][i] = None

        db['seats'] = seats
        save_db(db)

        return redirect(url_for('index', cancelled=1))

    return render_template('thank_you.html', mode='cancel')


@app.route('/seating-chart')
def seating_chart():
    email = norm_email(request.args.get('email'))
    data = load_db()

    if not email or email not in data['rsvps']:
        return redirect(url_for('index', unknown=1))

    # Only this year's tables — the data file may hold leftover keys
    seats = {key: data['seats'][key] for key in TABLE_NAMES}
    table_titles = {key: f'Table {NUMBER_WORDS[i]}' for i, key in enumerate(TABLE_NAMES)}
    rsvp_data = data['rsvps'][email]
    has_guest = bool(rsvp_data.get('guest_list'))

    return render_template('seating_chart.html',
                           seats=seats,
                           email=email,
                           rsvp_data=rsvp_data,
                           has_guest=has_guest,
                           table_names=TABLE_NAMES,
                           table_titles=table_titles,
                           deadline_passed=seat_changes_closed(),
                           is_admin=bool(session.get('is_admin')),
                           deadline=SEAT_CHANGE_DEADLINE.strftime('%B %d, %Y'))


@app.route('/api/seat-info')
def seat_info():
    table = request.args.get('table')
    try:
        seat_index = int(request.args.get('seat', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid seat number'}), 400

    data = load_db()
    if table in TABLE_NAMES and 0 <= seat_index < table_size(table):
        occupant = data['seats'][table][seat_index]
        if occupant:
            return jsonify({
                'occupied': True,
                'occupant': f"{occupant['full_name']} {occupant['surname']}"
            })
        else:
            return jsonify({'occupied': False})

    return jsonify({'error': 'Invalid seat'}), 400


@app.route('/api/select-seat', methods=['POST'])
def select_seat():
    data = request.json or {}
    email = norm_email(data.get('email'))
    table = data.get('table')
    guest = data.get('guest')
    clear = data.get('clear')

    try:
        seat_index = int(data.get('seat', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid seat number'}), 400

    # Validate table and seat range (only this year's tables are bookable)
    if table not in TABLE_NAMES:
        return jsonify({'error': 'Invalid table'}), 400

    if not 0 <= seat_index < table_size(table):
        return jsonify({'error': 'Invalid seat number'}), 400

    # Guests can't change seats after the deadline; organisers can
    if seat_changes_closed():
        return jsonify({'error': 'Seat selection deadline has passed'}), 400

    db = load_db()

    # Validate user
    if email not in db['rsvps']:
        return jsonify({'error': 'Invalid user'}), 400

    seats = db['seats']
    rsvp_data = db['rsvps'][email]

    # Seats are keyed by email; guests share the user's email with a suffix
    target_email = email + '_guest' if guest else email

    # Remove the person from any previous seat
    for t in seats:
        for i, occupant in enumerate(seats[t]):
            if occupant and occupant.get('email') == target_email:
                seats[t][i] = None

    # Deselect only: stop after freeing the seat
    if clear:
        db['seats'] = seats
        save_db(db)
        return jsonify({'success': True, 'message': 'Seat deselected'})

    if seats[table][seat_index] is not None:
        return jsonify({'error': 'Seat is already taken'}), 400

    if guest:
        full_name = rsvp_data.get('guest_list', '').strip()
        surname = ''
    else:
        full_name = rsvp_data['full_name']
        surname = rsvp_data['surname']

    seats[table][seat_index] = {
        'email': target_email,
        'full_name': full_name,
        'surname': surname
    }
    db['seats'] = seats
    save_db(db)

    who = 'Guest seat' if guest else 'Seat'
    return jsonify({
        'success': True,
        'message': f'{who} assigned at {table_display(table)} - Seat {seat_index + 1}'
    })


@app.route('/success')
def success():
    email = norm_email(request.args.get('email'))
    data = load_db()

    if not email or email not in data['rsvps']:
        return redirect(url_for('index'))

    rsvp_data = data['rsvps'][email]

    # Find the user's seat and, if they bring a partner, the partner's seat
    seats = data['seats']
    user_seat = None
    guest_seat = None
    for table_name, table_seats in seats.items():
        for i, occupant in enumerate(table_seats):
            if not occupant:
                continue
            if occupant.get('email') == email:
                user_seat = {'table': table_display(table_name), 'seat': i + 1, 'key': table_name}
            elif occupant.get('email') == email + '_guest':
                guest_seat = {'table': table_display(table_name), 'seat': i + 1, 'key': table_name}

    partner_name = (rsvp_data.get('guest_list') or '').strip()
    has_partner = rsvp_data.get('bringing_guest') == 'yes' and bool(partner_name)

    return render_template('success.html',
                           rsvp_data=rsvp_data,
                           user_seat=user_seat,
                           guest_seat=guest_seat,
                           partner_name=partner_name if has_partner else None,
                           different_tables=bool(user_seat and guest_seat
                                                 and user_seat['key'] != guest_seat['key']),
                           deadline_passed=seat_changes_closed(),
                           deadline=SEAT_CHANGE_DEADLINE.strftime('%B %d, %Y'))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

def admin_required():
    """None if the session is authenticated, else a redirect/JSON error."""
    if session.get('is_admin'):
        return None
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not authorised'}), 403
    return redirect(url_for('admin'))


def find_seat(seats, target_email):
    """(table, index) where target_email is seated, else (None, None)."""
    for t, occupants in seats.items():
        for i, occ in enumerate(occupants):
            if occ and occ.get('email') == target_email:
                return t, i
    return None, None


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin'))
        return render_template('admin.html', authed=False, login_error='Incorrect password.')

    if not session.get('is_admin'):
        return render_template('admin.html', authed=False)

    data = load_db()
    seats = {key: data['seats'][key] for key in TABLE_NAMES}

    tables = []
    for i, key in enumerate(TABLE_NAMES, start=1):
        tables.append({
            'key': key,
            'number': f'Table {NUMBER_WORDS[i - 1]}',
            'name': TABLE_NAMES[key],
            'occupants': seats[key],
        })

    # Attendees (and their partners) who don't have a seat yet
    unseated = []
    for email, rsvp_data in data['rsvps'].items():
        if email in data['cancel']:
            continue
        name = f"{rsvp_data.get('full_name', '')} {rsvp_data.get('surname', '')}".strip()
        if find_seat(seats, email) == (None, None):
            unseated.append({'email': email, 'name': name})
        partner = (rsvp_data.get('guest_list') or '').strip()
        if rsvp_data.get('bringing_guest') == 'yes' and partner:
            if find_seat(seats, email + '_guest') == (None, None):
                unseated.append({'email': email + '_guest',
                                 'name': f'{partner} (guest of {name})'})

    return render_template('admin.html',
                           authed=True,
                           tables=tables,
                           unseated=unseated,
                           rsvps=data['rsvps'],
                           cancels=data['cancel'],
                           deadline=f'{SEAT_CHANGE_DEADLINE.day} {SEAT_CHANGE_DEADLINE:%B %Y}')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))


@app.route('/api/admin/move-seat', methods=['POST'])
def admin_move_seat():
    guard = admin_required()
    if guard:
        return guard

    payload = request.json or {}
    from_table = payload.get('from_table')
    to_table = payload.get('to_table')
    try:
        from_seat = int(payload.get('from_seat'))
        to_seat = int(payload.get('to_seat'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid seat number'}), 400

    if from_table not in TABLE_NAMES or to_table not in TABLE_NAMES:
        return jsonify({'error': 'Invalid table'}), 400
    if not (0 <= from_seat < table_size(from_table) and 0 <= to_seat < table_size(to_table)):
        return jsonify({'error': 'Invalid seat number'}), 400

    db = load_db()
    seats = db['seats']

    mover = seats[from_table][from_seat]
    if mover is None:
        return jsonify({'error': 'That seat is empty'}), 400

    # Occupied target means a swap; empty target is a plain move
    seats[from_table][from_seat] = seats[to_table][to_seat]
    seats[to_table][to_seat] = mover
    save_db(db)

    name = f"{mover.get('full_name', '')} {mover.get('surname', '')}".strip()
    action = 'swapped with' if seats[from_table][from_seat] else 'moved to'
    return jsonify({'success': True,
                    'message': f'{name} {action} {table_display(to_table)} - Seat {to_seat + 1}'})


@app.route('/api/admin/unseat', methods=['POST'])
def admin_unseat():
    guard = admin_required()
    if guard:
        return guard

    payload = request.json or {}
    table = payload.get('table')
    try:
        seat = int(payload.get('seat'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid seat number'}), 400

    if table not in TABLE_NAMES or not 0 <= seat < table_size(table):
        return jsonify({'error': 'Invalid seat'}), 400

    db = load_db()
    occ = db['seats'][table][seat]
    if occ is None:
        return jsonify({'error': 'That seat is already empty'}), 400

    db['seats'][table][seat] = None
    save_db(db)
    name = f"{occ.get('full_name', '')} {occ.get('surname', '')}".strip()
    return jsonify({'success': True, 'message': f'{name} removed from their seat'})


@app.route('/api/admin/assign-seat', methods=['POST'])
def admin_assign_seat():
    guard = admin_required()
    if guard:
        return guard

    payload = request.json or {}
    target_email = payload.get('email')  # may carry the _guest suffix
    table = payload.get('table')
    try:
        seat = int(payload.get('seat'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid seat number'}), 400

    if table not in TABLE_NAMES or not 0 <= seat < table_size(table):
        return jsonify({'error': 'Invalid seat'}), 400

    is_guest = str(target_email).endswith('_guest')
    base_email = target_email[:-len('_guest')] if is_guest else target_email

    db = load_db()
    if base_email not in db['rsvps']:
        return jsonify({'error': 'Unknown guest'}), 400

    seats = db['seats']
    if seats[table][seat] is not None:
        return jsonify({'error': 'Seat is already taken'}), 400

    rsvp_data = db['rsvps'][base_email]
    if is_guest:
        full_name, surname = (rsvp_data.get('guest_list') or '').strip(), ''
    else:
        full_name, surname = rsvp_data['full_name'], rsvp_data['surname']

    # Remove any previous seat they held before placing them
    old_table, old_seat = find_seat(seats, target_email)
    if old_table is not None:
        seats[old_table][old_seat] = None

    seats[table][seat] = {'email': target_email,
                          'full_name': full_name,
                          'surname': surname}
    save_db(db)
    return jsonify({'success': True,
                    'message': f'{full_name} seated at {table_display(table)} - Seat {seat + 1}'})


@app.route('/admin/export.csv')
def admin_export_csv():
    guard = admin_required()
    if guard:
        return guard

    data = load_db()
    seats = data['seats']

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Status', 'First Name', 'Surname', 'Email', 'Cellphone',
                     'Dietary Requirements', 'Food Allergies', 'Table', 'Seat',
                     'Guest Of', 'Submitted At'])

    for email, r in data['rsvps'].items():
        status = 'Cancelled' if email in data['cancel'] else 'Attending'
        table, seat = find_seat(seats, email)
        writer.writerow([status, r.get('full_name', ''), r.get('surname', ''),
                         email, r.get('cellphone', ''),
                         r.get('dietary_requirements', ''), r.get('food_allergies', ''),
                         table_display(table) if table else '',
                         seat + 1 if seat is not None else '',
                         '', r.get('submitted_at', '')])

        partner = (r.get('guest_list') or '').strip()
        if r.get('bringing_guest') == 'yes' and partner:
            g_table, g_seat = find_seat(seats, email + '_guest')
            writer.writerow([status, partner, '', '', '', '', '',
                             table_display(g_table) if g_table else '',
                             g_seat + 1 if g_seat is not None else '',
                             f"{r.get('full_name', '')} {r.get('surname', '')}".strip(),
                             ''])

    # Declines that never RSVP'd as attending
    for email, c in data['cancel'].items():
        if email in data['rsvps']:
            continue
        writer.writerow(['Declined', c.get('full_name', ''), '', email, '', '', '',
                         '', '', '', c.get('submitted_at', '')])

    filename = f"guest-list-{date.today().isoformat()}.csv"
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


if __name__ == '__main__':
    #app.run(host='0.0.0.0', port=5000, debug=True)
    app.run(debug=False)
