"""
WebSocket event handlers for the live job feed.
Uses flask-socketio for real-time bidirectional communication.
"""
from app import socketio, HAS_SOCKETIO

if HAS_SOCKETIO and socketio:
    @socketio.on('connect', namespace='/')
    def on_connect():
        print('[SocketIO] Client connected.')
        socketio.emit('connected', {'status': 'ok'}, namespace='/')

    @socketio.on('disconnect', namespace='/')
    def on_disconnect():
        print('[SocketIO] Client disconnected.')

    @socketio.on('subscribe_jobs', namespace='/')
    def on_subscribe(data=None):
        """Client requests current top jobs. Respond with latest 10."""
        from app.models import Job
        from sqlalchemy import desc
        jobs = Job.query.order_by(desc(Job.posted_date)).limit(10).all()
        payload = [{
            'id':      j.id,
            'title':   j.title,
            'company': j.company,
            'source':  j.source,
        } for j in jobs]
        socketio.emit('job_snapshot', {'jobs': payload}, namespace='/')
