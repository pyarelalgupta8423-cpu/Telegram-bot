from pymongo import MongoClient
from datetime import datetime
from config import MONGO_URI, DATABASE_NAME

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

class User:
    collection = db['users']
    
    @staticmethod
    def get_or_create(user_id, username=None, first_name=None):
        user = User.collection.find_one({'user_id': user_id})
        if not user:
            user = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'points': 0,
                'referral_code': str(user_id),
                'referred_by': None,
                'referrals': [],
                'completed_tasks': [],
                'join_date': datetime.now(),
                'is_active': True
            }
            User.collection.insert_one(user)
        return user
    
    @staticmethod
    def update_points(user_id, points):
        User.collection.update_one(
            {'user_id': user_id},
            {'$inc': {'points': points}}
        )
    
    @staticmethod
    def add_referral(user_id, referred_id):
        User.collection.update_one(
            {'user_id': user_id},
            {'$push': {'referrals': referred_id}}
        )
    
    @staticmethod
    def get_all_users():
        return list(User.collection.find())
    
    @staticmethod
    def get_user_stats():
        total = User.collection.count_documents({})
        total_points = User.collection.aggregate([
            {'$group': {'_id': None, 'total': {'$sum': '$points'}}}
        ])
        total_points = next(total_points, {}).get('total', 0)
        return {'total_users': total, 'total_points': total_points}

class Task:
    collection = db['tasks']
    
    @staticmethod
    def add_task(task_data):
        task = {
            'title': task_data.get('title'),
            'description': task_data.get('description', 'No description'),
            'type': task_data.get('type'),
            'points': task_data.get('points', 0),
            'data': task_data.get('data', {}),
            'status': 'active',
            'created_at': datetime.now()
        }
        return Task.collection.insert_one(task)
    
    @staticmethod
    def get_active_tasks():
        return list(Task.collection.find({'status': 'active'}))
    
    @staticmethod
    def remove_task(task_id):
        Task.collection.update_one(
            {'_id': task_id},
            {'$set': {'status': 'inactive'}}
        )
    
    @staticmethod
    def update_task_points(task_id, points):
        Task.collection.update_one(
            {'_id': task_id},
            {'$set': {'points': points}}
        )

class WithdrawRequest:
    collection = db['withdraw_requests']
    
    @staticmethod
    def create_request(user_id, points_used, requested_id_type='telegram_id'):
        # Get next serial number
        last_request = WithdrawRequest.collection.find_one(
            sort=[('serial_number', -1)]
        )
        serial_number = (last_request.get('serial_number', 0) + 1) if last_request else 1000
        
        request = {
            'user_id': user_id,
            'serial_number': serial_number,
            'points_used': points_used,
            'requested_id_type': requested_id_type,
            'status': 'pending',
            'provided_id': None,
            'token': f"ID-{serial_number}-{user_id}",
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        return WithdrawRequest.collection.insert_one(request)
    
    @staticmethod
    def get_pending_requests():
        return list(WithdrawRequest.collection.find({'status': 'pending'}).sort('created_at', 1))
    
    @staticmethod
    def get_request_by_serial(serial_number):
        return WithdrawRequest.collection.find_one({'serial_number': serial_number})
    
    @staticmethod
    def approve_request(request_id, provided_id):
        WithdrawRequest.collection.update_one(
            {'_id': request_id},
            {'$set': {
                'status': 'approved',
                'provided_id': provided_id,
                'updated_at': datetime.now()
            }}
        )
    
    @staticmethod
    def complete_request(request_id):
        WithdrawRequest.collection.update_one(
            {'_id': request_id},
            {'$set': {
                'status': 'completed',
                'updated_at': datetime.now()
            }}
        )
    
    @staticmethod
    def reject_request(request_id, reason=None):
        WithdrawRequest.collection.update_one(
            {'_id': request_id},
            {'$set': {
                'status': 'rejected',
                'rejection_reason': reason,
                'updated_at': datetime.now()
            }}
        )
    
    @staticmethod
    def get_user_requests(user_id):
        return list(WithdrawRequest.collection.find({'user_id': user_id}).sort('created_at', -1))
    
    @staticmethod
    def get_all_requests():
        return list(WithdrawRequest.collection.find().sort('created_at', -1))

class WithdrawSettings:
    collection = db['withdraw_settings']
    
    @staticmethod
    def get_settings():
        settings = WithdrawSettings.collection.find_one({})
        if not settings:
            settings = {
                'min_points': 100,
                'points_per_id': 50,
                'available_ids': [],
                'is_active': True
            }
            WithdrawSettings.collection.insert_one(settings)
        return settings
    
    @staticmethod
    def update_settings(settings):
        WithdrawSettings.collection.update_one(
            {},
            {'$set': settings},
            upsert=True
        )
    
    @staticmethod
    def add_available_id(id_value):
        settings = WithdrawSettings.get_settings()
        if id_value not in settings.get('available_ids', []):
            WithdrawSettings.collection.update_one(
                {},
                {'$push': {'available_ids': id_value}}
            )
            return True
        return False
    
    @staticmethod
    def remove_available_id(id_value):
        settings = WithdrawSettings.get_settings()
        if id_value in settings.get('available_ids', []):
            WithdrawSettings.collection.update_one(
                {},
                {'$pull': {'available_ids': id_value}}
            )
            return True
        return False

class Channel:
    collection = db['channels']
    
    @staticmethod
    def add_channel(channel_id, channel_name, member_count, added_by=None):
        Channel.collection.update_one(
            {'channel_id': channel_id},
            {'$set': {
                'channel_name': channel_name,
                'member_count': member_count,
                'added_by': added_by,
                'added_at': datetime.now()
            }},
            upsert=True
        )
    
    @staticmethod
    def get_all_channels():
        return list(Channel.collection.find())
    
    @staticmethod
    def update_member_count(channel_id, member_count):
        Channel.collection.update_one(
            {'channel_id': channel_id},
            {'$set': {'member_count': member_count}}
        )

class Broadcast:
    collection = db['broadcasts']
    
    @staticmethod
    def create_broadcast(message_type, content, status='pending'):
        broadcast = {
            'message_type': message_type,
            'content': content,
            'status': status,
            'sent_count': 0,
            'failed_count': 0,
            'created_at': datetime.now()
        }
        return Broadcast.collection.insert_one(broadcast)
    
    @staticmethod
    def update_status(broadcast_id, status, sent_count, failed_count):
        Broadcast.collection.update_one(
            {'_id': broadcast_id},
            {'$set': {
                'status': status,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'completed_at': datetime.now()
            }}
        )
