import requests
import os
import json
import base64
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client, Client
from flask_cors import CORS

# --- SETUP ---
load_dotenv()
app = Flask(__name__)

# CORS configuration
app.config['CORS_HEADERS'] = 'Content-Type'
app.config['CORS_SUPPORTS_CREDENTIALS'] = True
app.config['CORS_ORIGINS'] = ['http://localhost:3000']

# Initialize CORS with the app
CORS(app, 
    resources={
        r"/api/*": {
            "origins": ["http://localhost:3000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": ["Authorization", "Content-Type", "X-Requested-With"],
            "supports_credentials": True,
            "expose_headers": ["Content-Disposition"]
        }
    },
    supports_credentials=True
)

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
            self.model = genai.GenerativeModel(
                model_name="gemini-2.5-flash"
            )

    def _get_user_rules(self, user_id):
        """Fetches all learned rules for a specific user from the Supabase database."""
        try:
            response = self.supabase.table('user_categories').select('category_name', 'keywords').eq('user_id', user_id).execute()
            
            user_rules = {}
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
            
            if response.data:
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

    # <<< --- BUG FIX 2: Changed 'image' to 'receipt' ---
    if 'receipt' not in request.files:
        return jsonify({'error': 'No image file provided. Use form-data with key "receipt".'}), 400

    image_file = request.files['receipt']
    # ---------------------------------------------------

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


@app.route('/api/groups', methods=['GET', 'OPTIONS'])
def get_groups():
    # Handle preflight request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
        
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
            # Verify the JWT token
            user_response = categorizer.supabase.auth.get_user(jwt)
            
            if not user_response or not hasattr(user_response, 'user') or not user_response.user:
                print("No user found in response")
                return jsonify({
                    'error': 'Invalid user token',
                    'details': 'No user data found in token'
                }), 401
                
            user_id = user_response.user.id
            print(f"Successfully authenticated user: {user_id}")
            
            # Get all groups where the user is a member
            print("Fetching user's groups...")
            result = categorizer.supabase.table('group_members') \
                .select('group_id, groups(*)') \
                .eq('user_id', user_id) \
                .execute()
            
            print(f"Found {len(result.data) if result.data else 0} groups for user {user_id}")
            
            if hasattr(result, 'error') and result.error:
                print(f"Query error: {result.error}")
                return jsonify({
                    'error': 'Failed to fetch groups',
                    'details': str(result.error)
                }), 500
                
            # Return the groups data
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
            
        # Transform the data to match the expected format
        groups = []
        for item in result.data:
            if 'groups' in item and item['groups']:
                group = item['groups']
                group_id = group.get('id')
                
                # Get member count for each group
                member_count_result = categorizer.supabase.table('group_members') \
                    .select('user_id') \
                    .eq('group_id', group_id) \
                    .execute()
                
                member_count = len(member_count_result.data or []) if hasattr(member_count_result, 'data') else 0
                
                # Get total expenses for this group
                expenses_result = categorizer.supabase.table('expenses') \
                    .select('amount') \
                    .eq('group_id', group_id) \
                    .execute()
                
                total_expenses = sum(float(exp.get('amount', 0)) for exp in expenses_result.data or []) if hasattr(expenses_result, 'data') else 0
                
                groups.append({
                    'id': group_id,
                    'name': group.get('name', 'Unnamed Group'),
                    'created_at': group.get('created_at'),
                    'updated_at': group.get('updated_at'),
                    'member_count': member_count,
                    'total_expenses': total_expenses
                })
            
        return jsonify({'groups': groups})
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in get_groups: {str(e)}\n{error_trace}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'trace': error_trace
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
        # Get the current user from the JWT
        user_response = categorizer.supabase.auth.get_user(jwt)
        if not user_response.user:
            return jsonify({'error': 'Invalid user token'}), 401
            
        user_id = user_response.user.id
        
        # Create the group
        group_data = {
            'name': data.get('name'),
            'created_by': user_id
        }
        
        print(f"Creating group with data: {group_data}")
        
        # Insert the group
        result = categorizer.supabase.table('groups').insert(group_data).execute()
        
        if hasattr(result, 'error') and result.error:
            print(f"Error creating group: {result.error}")
            return jsonify({'error': f'Database error: {str(result.error)}'}), 500
            
        # Get the created group
        group = result.data[0] if result.data and len(result.data) > 0 else None
        if not group:
            print("No group data returned after creation")
            return jsonify({'error': 'Failed to create group'}), 500
            
        print(f"Created group: {group}")
        
        # Add the creator as a member
        member_data = {
            'group_id': group['id'],
            'user_id': user_id
        }
        
        print(f"Adding group member: {member_data}")
        
        member_result = categorizer.supabase.table('group_members').insert(member_data).execute()
        
        if hasattr(member_result, 'error') and member_result.error:
            print(f"Error adding member to group: {member_result.error}")
            # If adding member fails, delete the created group to maintain consistency
            categorizer.supabase.table('groups').delete().eq('id', group['id']).execute()
            return jsonify({'error': f'Failed to add member to group: {str(member_result.error)}'}), 500
            
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
        import traceback
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
        # Verify the user is authenticated
        user_response = categorizer.supabase.auth.get_user(jwt)
        if not user_response.user:
            return jsonify({'error': 'Invalid user token'}), 401
            
        user_id = user_response.user.id
        
        # Check if user is a member of the group
        member_check = categorizer.supabase.table('group_members') \
            .select('*') \
            .eq('group_id', group_id) \
            .eq('user_id', user_id) \
            .execute()
        
        if not member_check.data or len(member_check.data) == 0:
            return jsonify({'error': 'You are not a member of this group'}), 403
        
        # Get all members of the group with their details
        members_result = categorizer.supabase.table('group_members') \
            .select('user_id, users!inner(*)') \
            .eq('group_id', group_id) \
            .execute()
        
        # Format the response
        members = []
        for member in members_result.data or []:
            user = member.get('users', {})
            members.append({
                'id': user.get('id'),
                'email': user.get('email'),
                'name': user.get('full_name') or user.get('email', '').split('@')[0],
                'balance': 0,  # You'll need to calculate this based on your expense logic
                'avatar': None  # Add avatar URL if available
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
        
        # Check if user is a member of the group
        member_check = categorizer.supabase.table('group_members') \
            .select('*') \
            .eq('group_id', group_id) \
            .eq('user_id', user_id) \
            .execute()
        
        if not member_check.data or len(member_check.data) == 0:
            return jsonify({'error': 'You are not a member of this group'}), 403
        
        # Get group details
        group_result = categorizer.supabase.table('groups') \
            .select('*') \
            .eq('id', group_id) \
            .execute()
        
        if not group_result.data or len(group_result.data) == 0:
            return jsonify({'error': 'Group not found'}), 404
        
        group = group_result.data[0]
        
        # Get members
        members_result = categorizer.supabase.table('group_members') \
            .select('user_id, auth.users(id, email, raw_user_meta_data)') \
            .eq('group_id', group_id) \
            .execute()
        
        # Get expenses for this group
        expenses_result = categorizer.supabase.table('expenses') \
            .select('*') \
            .eq('group_id', group_id) \
            .order('date', desc=True) \
            .execute()
        
        total_expenses = sum(float(exp.get('amount', 0)) for exp in expenses_result.data or []) if hasattr(expenses_result, 'data') else 0
        
        return jsonify({
            'group': group,
            'member_count': len(members_result.data or []) if hasattr(members_result, 'data') else 0,
            'total_expenses': total_expenses,
            'expenses': expenses_result.data or []
        }), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in get_group_detail: {str(e)}\n{error_trace}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'trace': error_trace
        }), 500

# Add this function to your Supabase database as a stored procedure
"""
CREATE OR REPLACE FUNCTION get_user_groups(user_uuid UUID)
RETURNS TABLE (
    id UUID,
    name TEXT,
    description TEXT,
    created_at TIMESTAMPTZ,
    created_by UUID,
    updated_at TIMESTAMPTZ,
    member_count BIGINT,
    role TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        g.id,
        g.name,
        g.description,
        g.created_at,
        g.created_by,
        g.updated_at,
        (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.id) as member_count,
        gm.role
    FROM 
        groups g
    JOIN 
        group_members gm ON g.id = gm.group_id
    WHERE 
        gm.user_id = user_uuid
    ORDER BY 
        g.updated_at DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
"""

@app.route('/api/groups/<group_id>/add-member', methods=['POST', 'OPTIONS'])
def add_group_member(group_id):
    if request.method == 'OPTIONS':
        # Handle preflight request
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
        
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization token'}), 401
    
    jwt = auth_header.split(' ')[1]
    
    try:
        # Verify the requesting user is authenticated
        user_response = categorizer.supabase.auth.get_user(jwt)
        requesting_user = user_response.user
        
        # Get the request data
        data = request.get_json()
        if not data or 'email' not in data:
            return jsonify({'error': 'Email is required'}), 400
            
        # Check if the group exists and the requesting user is a member
        group_response = categorizer.supabase.rpc('get_user_groups', {'user_uuid': requesting_user.id}).execute()
        group_exists = any(str(group['id']) == group_id for group in (group_response.data or []))
        
        if not group_exists:
            return jsonify({'error': 'Group not found or access denied'}), 404
            
        # Find the user by email in auth.users table
        try:
            # First try to find in public.users
            user_response = categorizer.supabase.table('users') \
                .select('*') \
                .eq('email', data['email'].lower()) \
                .maybe_single() \
                .execute()
            
            if not user_response.data:
                # If not found in public.users, try to find in auth.users
                try:
                    # This requires the get_user_by_email function to be created in Supabase
                    user_response = categorizer.supabase.rpc('get_user_by_email', {
                        'user_email': data['email'].lower()
                    }).execute()
                    
                    if not user_response.data or len(user_response.data) == 0:
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
                # User found in public.users
                user_data = user_response.data
                target_user = type('User', (), {
                    'id': user_data['id'],
                    'email': user_data['email'],
                    'user_metadata': user_data.get('user_metadata', {}) or {}
                })
            
        except Exception as e:
            print(f"Error in user lookup: {str(e)}")
            return jsonify({'error': 'Error looking up user information'}), 500
            
        # Check if user is already a member of the group
        existing_member = categorizer.supabase.table('group_members') \
            .select('*') \
            .eq('group_id', group_id) \
            .eq('user_id', target_user.id) \
            .maybe_single() \
            .execute()
            
        if existing_member.data:
            return jsonify({'error': 'User is already a member of this group'}), 409
            
        # Add user to the group
        member_data = {
            'group_id': group_id,
            'user_id': target_user.id,
            'role': 'member',
            'added_by': requesting_user.id,
            'created_at': 'now()'  # Let the database set the timestamp
        }
        
        result = categorizer.supabase.table('group_members').insert(member_data).execute()
        
        # Get user's full name from user_metadata or email
        user_metadata = getattr(target_user, 'user_metadata', {}) or {}
        full_name = user_metadata.get('full_name', data.get('name', data['email'].split('@')[0]))
        
        # Prepare response
        response = jsonify({
            'message': 'Member added successfully',
            'member': {
                'id': target_user.id,
                'email': target_user.email,
                'name': full_name,
                'role': 'member'
            }
        }), 201
        
    except Exception as e:
        print(f"Error adding member: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)