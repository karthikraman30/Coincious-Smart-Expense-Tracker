import requests
import os
import json
import base64
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client, Client
from flask_cors import CORS
import traceback # Import traceback for better error logging

# --- SETUP ---
load_dotenv()
app = Flask(__name__)

# --- CORS Configuration ---
from flask_cors import CORS

# Enable CORS for all routes under /api
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
            "supports_credentials": True,
            "expose_headers": ["Content-Disposition"],
            "max_age": 600
        }
    },
    supports_credentials=True
)

# Handle OPTIONS method for all routes
@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        # The CORS middleware will add the necessary headers
        return response


# Add this route after the CORS configuration
@app.route('/api/supabase/proxy/<path:subpath>', methods=['GET', 'POST'])
def supabase_proxy(subpath):
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Missing authorization'}), 401

    url = f"https{os.getenv('SUPABASE_URL').lstrip('https')}/functions/v1/make-server-7f88878c/{subpath}"
    
    headers = {
        'Authorization': auth_header,
        'Content-Type': 'application/json'
    }
    
    try:
        if request.method == 'GET':
            response = requests.get(url, headers=headers)
        else:
            response = requests.post(url, headers=headers, json=request.get_json())
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

class ExpenseCategorizer:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase URL and Key must be set in .env file")
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        self.model = None
        KEY = os.getenv('GEMINI_API_KEY')
        if KEY:
            genai.configure(api_key=KEY) 
            self.model = genai.GenerativeModel(model_name="gemini-2.5-flash")

    def _get_user_rules(self, user_id):
        """Fetches all learned rules for a specific user from the Supabase database."""
        try:
            response = self.supabase.table('user_categories').select('category_name', 'keywords').eq('user_id', user_id).execute()
            
            user_rules = {}
            if response and hasattr(response, 'data'):
                for item in response.data:
                    user_rules[item['category_name']] = item['keywords']
            return user_rules
        except Exception as e:
            print(f"Error fetching user rules: {e}")
            return {}

    def learn_new_rule(self, user_id, description, category):
        """Saves a new learned keyword for a specific user to the Supabase database."""
        print(f"Learning rule for user {user_id}: '{description}' -> '{category}'")
        keyword = description.lower()
        
        try:
            response = self.supabase.table('user_categories').select('keywords').eq('user_id', user_id).eq('category_name', category).execute()
            
            if response and hasattr(response, 'data') and response.data:
                existing_keywords = response.data[0]['keywords']
                if keyword not in existing_keywords:
                    new_keywords = existing_keywords + [keyword]
                    self.supabase.table('user_categories').update({'keywords': new_keywords}).eq('user_id', user_id).eq('category_name', category).execute()
                    print(f"Updated keywords for category '{category}'")
            else:
                self.supabase.table('user_categories').insert({
                    'user_id': user_id,
                    'category_name': category,
                    'keywords': [keyword]
                }).execute()
                print(f"Created new category rule for '{category}'")

        except Exception as e:
            print(f"Error saving new rule to Supabase: {e}")

    def parse_bill_image(self, image_bytes, mime_type):
        if not self.model:
            raise RuntimeError("Gemini model not configured")

        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        system_prompt = (
            "You are a precise receipt/bill parser. Extract fields and return STRICT JSON only. "
            "Fields: vendor_name, issue_date, due_date, subtotal, tax, tip, total, currency, "
            "line_items (name, quantity, unit_price, line_total), payment_method, address, "
            "category_guess, notes. Use null for unknowns. Dates ISO-8601. Numbers as floats. "
            "currency as 3-letter code if visible, else null."
        )

        content = [
            system_prompt,
            {
                "mime_type": mime_type,
                "data": base64_image
            },
            (
                "Respond ONLY with JSON in this schema: {\n"
                "  \"vendor_name\": string|null,\n"
                "  \"issue_date\": string|null,\n"
                "  \"due_date\": string|null,\n"
                "  \"subtotal\": number|null,\n"
                "  \"tax\": number|null,\n"
                "  \"tip\": number|null,\n"
                "  \"total\": number|null,\n"
                "  \"currency\": string|null,\n"
                "  \"payment_method\": string|null,\n"
                "  \"address\": string|null,\n"
                "  \"category_guess\": string|null,\n"
                "  \"notes\": string|null,\n"
                "  \"line_items\": [ { \"name\": string, \"quantity\": number|null, \"unit_price\": number|null, \"line_total\": number|null } ]\n"
                "}"
            )
        ]

        response = self.model.generate_content(content)
        raw_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)


    def find_category(self, user_id, description):
        """Main categorization logic: User's DB -> GenAI Fallback -> Learn."""
        lower_desc = description.lower()
        
        user_rules = self._get_user_rules(user_id)
        for category, keywords in user_rules.items():
            if any(key in lower_desc for key in keywords):
                return {"category": category, "source": "user_dictionary"}

        if not self.model:
            return {"category": "Other", "source": "no_ai_fallback"}
            
        print(f"'{description}' not in user rules. Asking AI...")
        prompt = self._build_ai_prompt(description, list(user_rules.keys()))
        
        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip().replace("```json", "").replace("```", "").strip()
            ai_result = json.loads(raw_text)
            
            ai_category = ai_result.get("category")

            if ai_category and ai_category != "Other":
                self.learn_new_rule(user_id, description, ai_category)
                return {"category": ai_category, "source": "ai"}

        except Exception as e:
            print(f"AI call failed: {e}. Defaulting to 'Other'.")

        return {"category": "Other", "source": "default"}

    def _build_ai_prompt(self, description, known_categories):
        """Builds the prompt for the Gemini AI."""
        base_categories = ["Food & Dining", "Transportation", "Shopping", "Bills & Utilities", "Entertainment", "Health & Wellness"]
        all_categories = list(set(known_categories + base_categories)) 
        return f"""
        Analyze the expense description: "{description}"

        My current categories are: {", ".join(all_categories)}.

        If one of those is a perfect fit, use it. 
        However, if you think a better, more specific category is needed (like 'Education' for 'college fees'), you are encouraged to create one.

        IMPORTANT: Respond ONLY with a JSON object in the format: {{"category": "CATEGORY_NAME"}}
        """

categorizer = ExpenseCategorizer()

@app.route('/api/categorize', methods=['POST'])
def api_categorize():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization token'}), 401
    
    jwt = auth_header.split(' ')[1]
    
    try:
        user_response = categorizer.supabase.auth.get_user(jwt)
        user = user_response.user
        if not user:
            raise Exception("Invalid user token")
    except Exception as e:
        return jsonify({'error': f'Authentication error: {str(e)}'}), 401
    
    form_data = request.form
    description = form_data.get('description', '').strip()

    if not description:
        return jsonify({'error': 'Description cannot be empty.'}), 400
    
    manual_category = form_data.get('category', '').strip()
    
    if manual_category:
        categorizer.learn_new_rule(user.id, description, manual_category)
        return jsonify({'status': 'learning_successful', 'learned': {description: manual_category}})
    else:
        result = categorizer.find_category(user.id, description)
        return jsonify(result)


@app.route('/api/parse-bill', methods=['POST'])
def api_parse_bill():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization token'}), 401

    jwt = auth_header.split(' ')[1]

    try:
        user_response = categorizer.supabase.auth.get_user(jwt)
        user = user_response.user
        if not user:
            raise Exception("Invalid user token")
    except Exception as e:
        return jsonify({'error': f'Authentication error: {str(e)}'}), 401

    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided. Use form-data with key "image".'}), 400

    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({'error': 'Empty filename for uploaded image.'}), 400

    try:
        image_bytes = image_file.read()
        mime_type = image_file.mimetype or 'image/jpeg'

        parsed = categorizer.parse_bill_image(image_bytes, mime_type)
        
        return jsonify({'parsed': parsed})
    except json.JSONDecodeError:
        return jsonify({'error': 'Model returned non-JSON or invalid JSON response.'}), 502
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': f'Failed to parse bill: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'Backend is running'})


@app.route('/api/groups', methods=['GET'])
def get_groups():
    auth_header = request.headers.get('Authorization')
    print(f"Auth header: {auth_header}")
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({
            'error': 'Missing or invalid authorization token',
            'details': 'No Bearer token provided in Authorization header'
        }), 401
    
    jwt = auth_header.split(' ')[1]
    
    try:
        if not jwt:
            return jsonify({
                'error': 'Invalid token',
                'details': 'Empty JWT token'
            }), 401
            
        print(f"JWT token received (first 10 chars): {jwt[:10]}...")
        
        try:
            user_response = categorizer.supabase.auth.get_user(jwt)
            
            if not user_response or not hasattr(user_response, 'user') or not user_response.user:
                print("No user found in response")
                return jsonify({
                    'error': 'Invalid user token',
                    'details': 'No user data found in token'
                }), 401
                
            user_id = user_response.user.id
            print(f"Successfully authenticated user: {user_id}")
            
            print("Fetching user's groups...")
            result = categorizer.supabase.table('group_members') \
                .select('group_id, groups(*)') \
                .eq('user_id', user_id) \
                .execute()
            
            if not result or not hasattr(result, 'data'):
                print(f"Query error or no data returned for user {user_id}")
                return jsonify({
                    'error': 'Failed to fetch groups',
                    'details': 'No data returned from database.'
                }), 500

            print(f"Found {len(result.data) if result.data else 0} groups for user {user_id}")
            
            return jsonify({
                'success': True,
                'groups': [group['groups'] for group in result.data] if result.data else []
            })
            
        except Exception as auth_error:
            print(f"Authentication error: {str(auth_error)}")
            return jsonify({
                'error': 'Authentication failed',
                'details': str(auth_error),
                'hint': 'Your session may have expired. Please try refreshing the page or logging in again.'
            }), 401
            
    except Exception as e:
        print(f"Unexpected error in get_groups: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

@app.route('/api/groups', methods=['POST'])
def create_group():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization token'}), 401
    
    jwt = auth_header.split(' ')[1]
    data = request.get_json()
    
    if not data.get('name'):
        return jsonify({'error': 'Group name is required'}), 400
    
    try:
        user_response = categorizer.supabase.auth.get_user(jwt)
        if not user_response.user:
            return jsonify({'error': 'Invalid user token'}), 401
            
        user_id = user_response.user.id
        
        group_data = {
            'name': data.get('name'),
            'created_by': user_id
        }
        
        print(f"Creating group with data: {group_data}")
        
        result = categorizer.supabase.table('groups').insert(group_data).execute()
        
        if not result or not hasattr(result, 'data') or not result.data:
            print(f"Error creating group, no data returned: {getattr(result, 'error', 'Unknown error')}")
            return jsonify({'error': f'Database error: {getattr(result, "error", "Failed to create group")}'}), 500
            
        group = result.data[0]
        print(f"Created group: {group}")
        
        # This is the minimal data required for a group_members insert
        # based on all the errors we've seen.
        member_data = {
            'group_id': group['id'],
            'user_id': user_id
        }
        
        print(f"Adding group member: {member_data}")
        
        member_result = categorizer.supabase.table('group_members').insert(member_data).execute()
        
        if not member_result or not hasattr(member_result, 'data'):
            print(f"Error adding member to group: {getattr(member_result, 'error', 'Unknown error')}")
            # Rollback: Delete the group we just created
            categorizer.supabase.table('groups').delete().eq('id', group['id']).execute()
            return jsonify({'error': f'Failed to add member to group: {getattr(member_result, "error", "Insert failed")}'}), 500
            
        print("Group and member created successfully")
            
        return jsonify({
            'group': {
                'id': group['id'],
                'name': group['name'],
                'created_at': group.get('created_at'),
                'updated_at': group.get('updated_at'),
                'member_count': 1
            }
        }), 201
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error in create_group: {str(e)}\n{error_trace}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'trace': error_trace
        }), 500

@app.route('/api/groups/<group_id>/members', methods=['GET'])
def get_group_members(group_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization token'}), 401
    
    jwt = auth_header.split(' ')[1]
    
    try:
        user_response = categorizer.supabase.auth.get_user(jwt)
        if not user_response.user:
            return jsonify({'error': 'Invalid user token'}), 401
            
        user_id = user_response.user.id
        
        member_check = categorizer.supabase.table('group_members') \
            .select('*') \
            .eq('group_id', group_id) \
            .eq('user_id', user_id) \
            .execute()
        
        if not member_check or not hasattr(member_check, 'data') or not member_check.data:
            return jsonify({'error': 'You are not a member of this group'}), 403
        
        members_result = categorizer.supabase.table('group_members') \
            .select('user_id, users!inner(*)') \
            .eq('group_id', group_id) \
            .execute()
        
        if not members_result or not hasattr(members_result, 'data'):
             print(f"Error getting members for group {group_id}: {getattr(members_result, 'error', 'No data returned')}")
             return jsonify({'error': 'Failed to fetch group members'}), 500

        members = []
        for member in members_result.data or []:
            user = member.get('users', {})
            members.append({
                'id': user.get('id'),
                'email': user.get('email'),
                'name': user.get('full_name') or user.get('email', '').split('@')[0],
                'balance': 0, 
                'avatar': None
            })
            
        return jsonify({'members': members})
        
    except Exception as e:
        print(f"Error getting group members: {str(e)}")
        return jsonify({'error': 'Failed to fetch group members', 'details': str(e)}), 500

@app.route('/api/groups/<group_id>', methods=['GET'])
def get_group_detail(group_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization token'}), 401
    
    jwt = auth_header.split(' ')[1]
    
    try:
        user_response = categorizer.supabase.auth.get_user(jwt)
        if not user_response.user:
            return jsonify({'error': 'Invalid user token'}), 401
            
        user_id = user_response.user.id
        
        member_check = categorizer.supabase.table('group_members') \
            .select('*') \
            .eq('group_id', group_id) \
            .eq('user_id', user_id) \
            .execute()
        
        if not member_check or not hasattr(member_check, 'data') or not member_check.data:
            return jsonify({'error': 'You are not a member of this group'}), 403
        
        group_result = categorizer.supabase.table('groups') \
            .select('*') \
            .eq('id', group_id) \
            .execute()
        
        if not group_result or not hasattr(group_result, 'data') or not group_result.data:
            return jsonify({'error': 'Group not found'}), 404
        
        group = group_result.data[0]
        
        members_result = categorizer.supabase.table('group_members') \
            .select('user_id, users!inner(*)') \
            .eq('group_id', group_id) \
            .execute()
        
        expenses_result = categorizer.supabase.table('expenses') \
            .select('*') \
            .eq('group_id', group_id) \
            .order('date', desc=True) \
            .execute()
        
        total_expenses = sum(float(exp.get('amount', 0)) for exp in (expenses_result.data or [])) if expenses_result and hasattr(expenses_result, 'data') else 0
        member_count = len(members_result.data or []) if members_result and hasattr(members_result, 'data') else 0
        
        return jsonify({
            'group': group,
            'member_count': member_count,
            'total_expenses': total_expenses,
            'expenses': expenses_result.data or [] if expenses_result and hasattr(expenses_result, 'data') else []
        }), 200
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error in get_group_detail: {str(e)}\n{error_trace}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'trace': error_trace
        }), 500


# --- THIS IS THE NEW FUNCTION YOU NEED TO ADD ---
@app.route('/api/groups/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization token'}), 401
    
    jwt = auth_header.split(' ')[1]
    
    try:
        user_response = categorizer.supabase.auth.get_user(jwt)
        if not user_response.user:
            return jsonify({'error': 'Invalid user token'}), 401
        user_id = user_response.user.id
        
        # --- Permission Check: Only the creator can delete ---
        # 1. Fetch the group to see who created it
        print(f"User {user_id} attempting to delete group {group_id}")
        group_result = categorizer.supabase.table('groups') \
            .select('created_by') \
            .eq('id', group_id) \
            .maybe_single() \
            .execute()
        
        if not group_result or not hasattr(group_result, 'data') or not group_result.data:
            print("Group not found")
            return jsonify({'error': 'Group not found'}), 404
            
        group_data = group_result.data
        print(f"Group created by: {group_data.get('created_by')}")
        
        # 2. Compare creator ID with the current user's ID
        if str(group_data.get('created_by')) != str(user_id):
            print("Permission denied")
            return jsonify({'error': 'You do not have permission to delete this group'}), 403 # 403 Forbidden
        
        # --- If permission check passes, delete the group ---
        # This assumes your Supabase tables (group_members, expenses)
        # have "ON DELETE CASCADE" set for the group_id foreign key.
        print(f"Permission granted. Deleting group {group_id}...")
        delete_result = categorizer.supabase.table('groups') \
            .delete() \
            .eq('id', group_id) \
            .execute()

        if not delete_result or not hasattr(delete_result, 'data') or not delete_result.data:
             print(f"Delete failed or group not found during delete: {getattr(delete_result, 'error', 'Unknown error')}")
             return jsonify({'error': 'Failed to delete group, or group not found'}), 500

        print(f"Group {group_id} deleted successfully.")
        return jsonify({'message': 'Group deleted successfully'}), 200
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error in delete_group: {str(e)}\n{error_trace}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'trace': error_trace
        }), 500
# --- END OF NEW FUNCTION ---


@app.route('/api/groups/<group_id>/add-member', methods=['POST'])
def add_group_member(group_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization token'}), 401
    
    jwt = auth_header.split(' ')[1]
    
    try:
        user_response = categorizer.supabase.auth.get_user(jwt)
        requesting_user = user_response.user
        
        data = request.get_json()
        if not data or 'email' not in data:
            return jsonify({'error': 'Email is required'}), 400
            
        group_response = categorizer.supabase.rpc('get_user_groups', {'user_uuid': requesting_user.id}).execute()
        
        if not group_response or not hasattr(group_response, 'data'):
            print(f"Error calling rpc get_user_groups for user {requesting_user.id}")
            return jsonify({'error': 'Failed to verify group membership'}), 500

        group_exists = any(str(group['id']) == group_id for group in (group_response.data or []))
        
        if not group_exists:
            return jsonify({'error': 'Group not found or access denied'}), 404
            
        # Find the user by email
        try:
            user_response = categorizer.supabase.table('users') \
                .select('*') \
                .eq('email', data['email'].lower()) \
                .maybe_single() \
                .execute()
            
            user_data = user_response.data if user_response and hasattr(user_response, 'data') else None

            if not user_data:
                # If not found in public.users, try to find in auth.users
                try:
                    user_response = categorizer.supabase.rpc('get_user_by_email', {
                        'user_email': data['email'].lower()
                    }).execute()
                    
                    if not user_response or not hasattr(user_response, 'data') or not user_response.data:
                        return jsonify({'error': 'User with this email does not exist'}), 404
                        
                    user_data = user_response.data[0]
                    target_user = type('User', (), {
                        'id': user_data['id'],
                        'email': user_data['email'],
                        'user_metadata': user_data.get('raw_user_meta_data', {}) or {}
                    })
                    
                except Exception as e:
                    print(f"Error looking up user in auth.users: {str(e)}")
                    return jsonify({'error': 'Error looking up user information'}), 500
            else:
                target_user = type('User', (), {
                    'id': user_data['id'],
                    'email': user_data['email'],
                    'user_metadata': user_data.get('user_metadata', {}) or {}
                })
            
        except Exception as e:
            print(f"Error in user lookup: {str(e)}")
            return jsonify({'error': 'Error looking up user information'}), 500
            
        existing_member = categorizer.supabase.table('group_members') \
            .select('*') \
            .eq('group_id', group_id) \
            .eq('user_id', target_user.id) \
            .maybe_single() \
            .execute()
            
        if existing_member and hasattr(existing_member, 'data') and existing_member.data:
            return jsonify({'error': 'User is already a member of this group'}), 409
            
        #
        # --- FIX ---
        #
        # This is now the absolute minimal data to insert,
        # which should match your 'group_members' table structure.
        #
        member_data = {
            'group_id': group_id,
            'user_id': target_user.id
        }
        
        try:
            result = categorizer.supabase.table('group_members').insert(member_data).execute()
        except Exception as e:
            print(f"Error during final member insert: {e}")
            raise e # Re-raise the error

        if not result or not hasattr(result, 'data'):
             print(f"Error inserting new member: {getattr(result, 'error', 'Unknown error')}")
             return jsonify({'error': 'Failed to add member to group database'}), 500

        user_metadata = getattr(target_user, 'user_metadata', {}) or {}
        full_name = user_metadata.get('full_name', data.get('name', data['email'].split('@')[0]))
        
        return jsonify({
            'message': 'Member added successfully',
            'member': {
                'id': target_user.id,
                'email': target_user.email,
                'name': full_name,
                'role': 'member' # This is just for the frontend, not the database
            }
        }), 201
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error adding member: {str(e)}\n{error_trace}")
        return jsonify({'error': str(e), 'trace': error_trace}), 500

@app.route('/api/expenses', methods=['GET', 'OPTIONS'])
def get_expenses():
    # Handle OPTIONS request
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response
        
    # Get the group_id from query parameters
    group_id = request.args.get('group_id')
    if not group_id:
        return jsonify({'error': 'Missing group_id parameter'}), 400

    try:
        # Get the current user
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Missing authorization'}), 401

        # Initialize Supabase client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        if not supabase_url or not supabase_key:
            return jsonify({'error': 'Server configuration error'}), 500
            
        supabase = create_client(supabase_url, supabase_key)
        
        # Verify the user's token
        user = supabase.auth.get_user(auth_header.split(' ')[1])
        
        if not user:
            return jsonify({'error': 'Invalid user'}), 401

        # Query expenses for the group
        response = supabase.table('expenses') \
            .select('*') \
            .eq('group_id', group_id) \
            .order('created_at', desc=True) \
            .execute()

        if hasattr(response, 'error') and response.error:
            return jsonify({'error': str(response.error)}), 500

        # Get member details for each expense
        expenses = []
        for expense in response.data:
            # Safely get the user who paid - try different possible column names
            paid_by_id = None
            paid_by_name = 'Unknown'
            
            # Try different possible column names
            for field in ['paid_by', 'paid_by_user_id', 'user_id', 'created_by']:
                if field in expense and expense[field]:
                    paid_by_id = expense[field]
                    break
                    
            if paid_by_id:
                try:
                    paid_by_user = supabase.auth.admin.get_user_by_id(str(paid_by_id))
                    if hasattr(paid_by_user, 'user') and paid_by_user.user:
                        paid_by_name = paid_by_user.user.email or f"User {str(paid_by_id)[:8]}"
                except Exception as e:
                    print(f"Error getting user {paid_by_id}: {str(e)}")
                    paid_by_name = f"User {str(paid_by_id)[:8]}" if paid_by_id else 'Unknown'
            
            # Get split members
            split_among = []
            if expense.get('split_among'):
                for user_id in expense['split_among']:
                    try:
                        user_data = supabase.auth.admin.get_user_by_id(user_id)
                        if hasattr(user_data, 'user') and user_data.user:
                            split_among.append({
                                'id': user_id,
                                'name': user_data.user.email or f"User {user_id[:8]}"
                            })
                    except Exception as e:
                        print(f"Error getting user {user_id}: {str(e)}")
                        split_among.append({
                            'id': user_id,
                            'name': f"User {user_id[:8]}"
                        })
            
            # Build expense data with safe field access
            expense_data = {
                'id': expense.get('id'),
                'description': expense.get('description', 'No description'),
                'amount': float(expense.get('amount', 0)),
                'category': expense.get('category', 'Other'),
                'date': expense.get('created_at'),
                'paid_by': {
                    'id': paid_by_id,
                    'name': paid_by_name
                },
                'split_among': split_among,
                'receipt_url': expense.get('receipt_url')
            }
            
            # Only add if we have a valid ID
            if expense_data['id']:
                expenses.append(expense_data)
            else:
                print(f"Skipping expense with invalid ID: {expense}")

        return jsonify({'expenses': expenses})

    except Exception as e:
        print(f"Error fetching expenses: {str(e)}")
        traceback.print_exc()  # This will print the full traceback
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)