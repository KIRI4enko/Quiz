import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.room_group_name = f"game_{self.session_id}"

        if not await self.session_exists(self.session_id):
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()
        await self.send_current_state()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = data.get("action")
        user = self.scope["user"]

        moderator_actions = {
            "moderator_start_game": self.handle_ws_moderator_start_game,
            "moderator_start_question": self.handle_ws_moderator_start_question,
            "moderator_end_question": self.handle_ws_moderator_end_question,
            "moderator_show_correct_answer": self.handle_ws_moderator_show_correct_answer,
            "moderator_end_game": self.handle_ws_moderator_end_game,
        }
        if action in moderator_actions:
            await moderator_actions[action](user)
            return

        if action == "answer":
            await self.handle_answer(data)
        elif action == "request_state":
            await self.send_current_state()

    async def handle_ws_moderator_start_game(self, user):
        result = await self.ws_moderator_start_game(int(self.session_id), user)
        if not result["ok"]:
            await self.send(text_data=json.dumps({"type": "moderator_error", "message": result["error"]}))
            return
        await self.broadcast_room_state()

    async def handle_ws_moderator_start_question(self, user):
        result = await self.ws_moderator_start_question(int(self.session_id), user)
        if not result["ok"]:
            await self.send(text_data=json.dumps({"type": "moderator_error", "message": result["error"]}))
            return
        payload = result["new_question_payload"]
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "new_question",
                **payload,
            },
        )
        await self.broadcast_room_state()

    async def handle_ws_moderator_end_question(self, user):
        result = await self.ws_moderator_end_question(int(self.session_id), user)
        if not result["ok"]:
            await self.send(text_data=json.dumps({"type": "moderator_error", "message": result["error"]}))
            return
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "game_message",
                "message": {
                    "type": "question_ended",
                    "game_question_id": result["game_question_id"],
                },
            },
        )
        await self.broadcast_room_state()

    async def handle_ws_moderator_show_correct_answer(self, user):
        result = await self.ws_moderator_show_correct_answer(int(self.session_id), user)
        if not result["ok"]:
            await self.send(text_data=json.dumps({"type": "moderator_error", "message": result["error"]}))
            return
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "game_message",
                "message": {
                    "type": "show_correct_answer",
                    "game_question_id": result["game_question_id"],
                    "correct_choice_id": result["correct_choice_id"],
                    "correct_text": result["correct_text"],
                },
            },
        )
        await self.broadcast_room_state()

    async def handle_ws_moderator_end_game(self, user):
        result = await self.ws_moderator_end_game(int(self.session_id), user)
        if not result["ok"]:
            await self.send(text_data=json.dumps({"type": "moderator_error", "message": result["error"]}))
            return
        await self.broadcast_room_state()

    async def broadcast_room_state(self):
        state = await self.get_current_state()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "broadcast_state",
                "state": state,
            },
        )

    async def handle_answer(self, data):
        team_id = data.get("team_id")
        game_question_id = data.get("game_question_id")
        choice_id = data.get("choice_id")
        elapsed = data.get("elapsed")

        can_answer, game_question = await self.can_answer(game_question_id, team_id, elapsed)
        if not can_answer:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "Ответ не может быть принят",
                    }
                )
            )
            return

        choice = await self.get_choice(choice_id)
        is_correct = choice.is_correct if choice else False

        await self.save_answer(team_id, game_question, choice, elapsed)

        scores = await self.update_scoreboard()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "update_scores",
                "scores": scores,
            },
        )

        await self.send(
            text_data=json.dumps(
                {
                    "type": "answer_result",
                    "correct": is_correct,
                    "elapsed": elapsed,
                }
            )
        )

    async def send_current_state(self):
        state = await self.get_current_state()
        await self.send(text_data=json.dumps({"type": "state", **state}))

    async def game_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    async def new_question(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "new_question",
                    "game_question_id": event["game_question_id"],
                    "question_text": event["question_text"],
                    "image_url": event.get("image_url"),
                    "choices": event["choices"],
                    "time_limit": event["time_limit"],
                    "start_time": event["start_time"],
                }
            )
        )

    async def update_scores(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "scores",
                    "scores": event["scores"],
                }
            )
        )

    async def game_ended(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "game_ended",
                    "final_scores": event["scores"],
                }
            )
        )

    async def broadcast_state(self, event):
        await self.send(text_data=json.dumps({"type": "state", **event["state"]}))

    @database_sync_to_async
    def session_exists(self, session_id):
        from quiz.models import GameSession

        return GameSession.objects.filter(id=session_id).exists()

    @database_sync_to_async
    def can_answer(self, game_question_id, team_id, elapsed):
        from quiz.models import GameQuestion, Answer

        try:
            game_question = GameQuestion.objects.select_related("game_session", "question").get(id=game_question_id)
        except GameQuestion.DoesNotExist:
            return False, None

        if game_question.game_session.status != "active":
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
        team_session, _ = TeamSession.objects.get_or_create(team=team, game_session=game_question.game_session)
        Answer.objects.create(
            team_session=team_session,
            game_question=game_question,
            choice=choice,
            elapsed_time=elapsed,
            is_correct=choice.is_correct if choice else False,
        )

    @database_sync_to_async
    def update_scoreboard(self):
        from django.db.models import Sum
        from quiz.models import GameSession

        session = GameSession.objects.get(id=self.session_id)
        scores = []
        for team_session in session.teams.all():
            correct_count = team_session.answers.filter(is_correct=True).count()
            total_time = team_session.answers.aggregate(total=Sum("elapsed_time"))["total"] or 0
            scores.append(
                {
                    "team_id": team_session.team.id,
                    "team_name": team_session.team.name,
                    "color": team_session.team.color,
                    "correct": correct_count,
                    "total_time": total_time,
                }
            )
        scores.sort(key=lambda x: (-x["correct"], x["total_time"]))
        return scores

    @database_sync_to_async
    def get_current_state(self):
        from django.db.models import Sum
        from quiz.models import GameSession, Choice

        session = (
            GameSession.objects.select_related("current_game_question", "current_game_question__question")
            .get(id=self.session_id)
        )

        scores = []
        for team_session in session.teams.all():
            correct_count = team_session.answers.filter(is_correct=True).count()
            total_time = team_session.answers.aggregate(total=Sum("elapsed_time"))["total"] or 0
            scores.append(
                {
                    "team_id": team_session.team.id,
                    "team_name": team_session.team.name,
                    "color": team_session.team.color,
                    "correct": correct_count,
                    "total_time": total_time,
                }
            )
        scores.sort(key=lambda x: (-x["correct"], x["total_time"]))

        if session.status == "prep":
            game_stage = "prep"
        elif session.status == "finished":
            game_stage = "finished"
        elif session.status == "active":
            cq = session.current_game_question
            if cq and cq.start_time:
                time_passed = (timezone.now() - cq.start_time).total_seconds()
                limit = cq.question.time_limit
                if time_passed <= limit:
                    game_stage = "active_question"
                else:
                    game_stage = "active_question_time_up"
            else:
                game_stage = "active_idle"
        else:
            game_stage = "unknown"

        question_data = None
        cq = session.current_game_question
        if cq and cq.start_time:
            time_passed = (timezone.now() - cq.start_time).total_seconds()
            limit = cq.question.time_limit
            choices = [
                {"id": c.id, "text": c.text}
                for c in Choice.objects.filter(question=cq.question).order_by("order")
            ]
            question_data = {
                "game_question_id": cq.id,
                "question_text": cq.question.text,
                "image_url": cq.question.image.url if cq.question.image else None,
                "choices": choices,
                "time_limit": limit,
                "remaining_time": max(0, limit - time_passed),
                "start_time": cq.start_time.isoformat(),
                "timed_out": time_passed > limit,
            }

        return {
            "session_status": session.status,
            "game_stage": game_stage,
            "scores": scores,
            "current_question": question_data,
        }

    @database_sync_to_async
    def ws_moderator_start_game(self, session_id, user):
        from quiz.models import GameSession

        if not user.is_authenticated or not getattr(user, "moderator_profile", None):
            return {"ok": False, "error": "Недостаточно прав модератора."}

        try:
            session = GameSession.objects.get(id=session_id)
        except GameSession.DoesNotExist:
            return {"ok": False, "error": "Сессия не найдена."}

        if session.status != "prep":
            return {"ok": False, "error": "Игра уже запущена или завершена."}
        if not session.game_questions.exists():
            return {"ok": False, "error": "Нельзя запустить игру без вопросов."}

        session.status = "active"
        session.start_time = timezone.now()
        session.save()
        return {"ok": True}

    @database_sync_to_async
    def ws_moderator_start_question(self, session_id, user):
        from quiz.models import GameSession

        if not user.is_authenticated or not getattr(user, "moderator_profile", None):
            return {"ok": False, "error": "Недостаточно прав модератора."}

        try:
            session = GameSession.objects.get(id=session_id)
        except GameSession.DoesNotExist:
            return {"ok": False, "error": "Сессия не найдена."}

        if session.status != "active":
            return {"ok": False, "error": "Игра не активна."}

        next_game_question = session.game_questions.filter(start_time__isnull=True).order_by("order").first()
        if not next_game_question:
            return {"ok": False, "error": "Нет больше вопросов."}

        next_game_question.start_time = timezone.now()
        next_game_question.save()
        session.current_game_question = next_game_question
        session.save()

        question = next_game_question.question
        payload = {
            "game_question_id": next_game_question.id,
            "question_text": question.text,
            "image_url": question.image.url if question.image else None,
            "choices": [{"id": c.id, "text": c.text} for c in question.choices.all().order_by("order")],
            "time_limit": question.time_limit,
            "start_time": next_game_question.start_time.isoformat(),
        }
        return {"ok": True, "new_question_payload": payload}

    @database_sync_to_async
    def ws_moderator_end_question(self, session_id, user):
        from quiz.models import GameSession

        if not user.is_authenticated or not getattr(user, "moderator_profile", None):
            return {"ok": False, "error": "Недостаточно прав модератора."}

        try:
            session = GameSession.objects.get(id=session_id)
        except GameSession.DoesNotExist:
            return {"ok": False, "error": "Сессия не найдена."}

        if session.status != "active" or not session.current_game_question:
            return {"ok": False, "error": "Нет активного вопроса."}

        current_gq = session.current_game_question
        gq_id = current_gq.id
        session.current_game_question = None
        session.save()
        return {"ok": True, "game_question_id": gq_id}

    @database_sync_to_async
    def ws_moderator_show_correct_answer(self, session_id, user):
        from quiz.models import GameSession

        if not user.is_authenticated or not getattr(user, "moderator_profile", None):
            return {"ok": False, "error": "Недостаточно прав модератора."}

        try:
            session = GameSession.objects.get(id=session_id)
        except GameSession.DoesNotExist:
            return {"ok": False, "error": "Сессия не найдена."}

        last_gq = session.game_questions.filter(start_time__isnull=False).order_by("-start_time").first()
        if not last_gq:
            return {"ok": False, "error": "Нет завершённых вопросов."}

        correct_choice = last_gq.question.choices.filter(is_correct=True).first()
        if not correct_choice:
            return {"ok": False, "error": "У вопроса нет правильного ответа."}

        return {
            "ok": True,
            "game_question_id": last_gq.id,
            "correct_choice_id": correct_choice.id,
            "correct_text": correct_choice.text,
        }

    @database_sync_to_async
    def ws_moderator_end_game(self, session_id, user):
        from django.db.models import Sum
        from quiz.models import GameSession

        if not user.is_authenticated or not getattr(user, "moderator_profile", None):
            return {"ok": False, "error": "Недостаточно прав модератора."}

        try:
            session = GameSession.objects.get(id=session_id)
        except GameSession.DoesNotExist:
            return {"ok": False, "error": "Сессия не найдена."}

        if session.status != "active":
            return {"ok": False, "error": "Игра не активна."}

        session.current_game_question = None
        session.status = "finished"
        session.end_time = timezone.now()
        session.save()

        scores = []
        for team_session in session.teams.all():
            correct_count = team_session.answers.filter(is_correct=True).count()
            total_time = team_session.answers.aggregate(total=Sum("elapsed_time"))["total"] or 0
            scores.append(
                {
                    "team_id": team_session.team.id,
                    "team_name": team_session.team.name,
                    "color": team_session.team.color,
                    "correct": correct_count,
                    "total_time": total_time,
                }
            )
        scores.sort(key=lambda x: (-x["correct"], x["total_time"]))
        return {"ok": True, "scores": scores}
