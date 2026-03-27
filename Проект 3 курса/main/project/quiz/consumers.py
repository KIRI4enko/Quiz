import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'game_{self.session_id}'
        
        if not await self.session_exists(self.session_id):
            await self.close()
            return
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        await self.send_current_state()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')
        
        if action == 'answer':
            await self.handle_answer(data)
        elif action == 'request_state':
            await self.send_current_state()
    
    async def handle_answer(self, data):
        team_id = data.get('team_id')
        game_question_id = data.get('game_question_id')
        choice_id = data.get('choice_id')
        elapsed = data.get('elapsed')
        
        can_answer, game_question = await self.can_answer(game_question_id, team_id, elapsed)
        if not can_answer:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Ответ не может быть принят'
            }))
            return
        
        choice = await self.get_choice(choice_id)
        is_correct = choice.is_correct if choice else False
        
        await self.save_answer(team_id, game_question, choice, elapsed)
        
        # Получаем обновлённый счёт и рассылаем всем
        scores = await self.update_scoreboard()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'update_scores',
                'scores': scores
            }
        )
        
        await self.send(text_data=json.dumps({
            'type': 'answer_result',
            'correct': is_correct,
            'elapsed': elapsed
        }))

    async def send_current_state(self):
        state = await self.get_current_state()
        await self.send(text_data=json.dumps({
            'type': 'state',
            **state
        }))

    async def game_message(self, event):
        await self.send(text_data=json.dumps(event['message']))
    
    async def new_question(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_question',
            'game_question_id': event['game_question_id'],
            'question_text': event['question_text'],
            'choices': event['choices'],
            'time_limit': event['time_limit'],
            'start_time': event['start_time']
        }))
    
    async def update_scores(self, event):
        await self.send(text_data=json.dumps({
            'type': 'scores',
            'scores': event['scores']
        }))
    
    async def game_ended(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_ended',
            'final_scores': event['scores']
        }))

    # --- Асинхронные методы работы с БД ---
    @database_sync_to_async
    def session_exists(self, session_id):
        from quiz.models import GameSession
        return GameSession.objects.filter(id=session_id).exists()
    
    @database_sync_to_async
    def can_answer(self, game_question_id, team_id, elapsed):
        from quiz.models import GameQuestion, Answer
        try:
            game_question = GameQuestion.objects.select_related('game_session', 'question').get(id=game_question_id)
        except GameQuestion.DoesNotExist:
            return False, None
        
        if game_question.game_session.status != 'active':
            return False, None
        if not game_question.start_time:
            return False, None
        
        time_passed = (timezone.now() - game_question.start_time).total_seconds()
        if time_passed > game_question.question.time_limit:
            return False, None
        
        if Answer.objects.filter(team_session__team_id=team_id, game_question=game_question).exists():
            return False, None
        
        if abs(elapsed - time_passed) > 2.0:
            return False, None
        
        return True, game_question
    
    @database_sync_to_async
    def get_choice(self, choice_id):
        from quiz.models import Choice
        try:
            return Choice.objects.get(id=choice_id)
        except Choice.DoesNotExist:
            return None
    
    @database_sync_to_async
    def save_answer(self, team_id, game_question, choice, elapsed):
        from quiz.models import Team, TeamSession, Answer
        team = Team.objects.get(id=team_id)
        team_session, _ = TeamSession.objects.get_or_create(
            team=team,
            game_session=game_question.game_session
        )
        Answer.objects.create(
            team_session=team_session,
            game_question=game_question,
            choice=choice,
            elapsed_time=elapsed,
            is_correct=choice.is_correct if choice else False
        )
    
    @database_sync_to_async
    def update_scoreboard(self):
        from django.db.models import Sum
        from quiz.models import GameSession
        session = GameSession.objects.get(id=self.session_id)
        scores = []
        for team_session in session.teams.all():
            correct_count = team_session.answers.filter(is_correct=True).count()
            total_time = team_session.answers.aggregate(total=Sum('elapsed_time'))['total'] or 0
            scores.append({
                'team_id': team_session.team.id,
                'team_name': team_session.team.name,
                'color': team_session.team.color,
                'correct': correct_count,
                'total_time': total_time
            })
        scores.sort(key=lambda x: (-x['correct'], x['total_time']))
        return scores
    
    @database_sync_to_async
    def get_current_state(self):
        from django.db.models import Sum
        from quiz.models import GameSession
        session = GameSession.objects.get(id=self.session_id)
        current_game_question = session.current_game_question
        
        scores = []
        for team_session in session.teams.all():
            correct_count = team_session.answers.filter(is_correct=True).count()
            total_time = team_session.answers.aggregate(total=Sum('elapsed_time'))['total'] or 0
            scores.append({
                'team_id': team_session.team.id,
                'team_name': team_session.team.name,
                'color': team_session.team.color,
                'correct': correct_count,
                'total_time': total_time
            })
        scores.sort(key=lambda x: (-x['correct'], x['total_time']))
        
        question_data = None
        if current_game_question and current_game_question.start_time:
            from quiz.models import Choice
            time_passed = (timezone.now() - current_game_question.start_time).total_seconds()
            if time_passed <= current_game_question.question.time_limit:
                choices = [
                    {'id': c.id, 'text': c.text}
                    for c in Choice.objects.filter(question=current_game_question.question).order_by('order')
                ]
                question_data = {
                    'game_question_id': current_game_question.id,
                    'question_text': current_game_question.question.text,
                    'choices': choices,
                    'time_limit': current_game_question.question.time_limit,
                    'remaining_time': max(0, current_game_question.question.time_limit - time_passed),
                    'start_time': current_game_question.start_time.isoformat()
                }
        
        return {
            'session_status': session.status,
            'scores': scores,
            'current_question': question_data
        }