from django.db import models
from django.utils import timezone

class Team(models.Model):
    """Команда-участник"""
    name = models.CharField('Название команды', max_length=100, unique=True)
    password = models.CharField('Пароль для входа', max_length=50)  # простой код, не для Django auth
    color = models.CharField('Цвет команды', max_length=7, default='#3498db')  # hex-код
    created_at = models.DateTimeField('Дата регистрации', auto_now_add=True)

    class Meta:
        verbose_name = 'Команда'
        verbose_name_plural = 'Команды'

    def __str__(self):
        return self.name


class Question(models.Model):
    """Вопрос викторины (без привязки к конкретной игре)"""
    text = models.TextField('Текст вопроса')
    time_limit = models.PositiveIntegerField('Время на ответ (сек)', default=60)
    image = models.ImageField('Изображение', upload_to='questions/', blank=True, null=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'

    def __str__(self):
        return f'{self.id}: {self.text}'


class Choice(models.Model):
    """Вариант ответа на вопрос"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices', verbose_name='Вопрос')
    text = models.CharField('Текст варианта', max_length=255)
    is_correct = models.BooleanField('Правильный?', default=False)
    order = models.PositiveIntegerField('Порядок отображения', default=0)

    class Meta:
        verbose_name = 'Вариант ответа'
        verbose_name_plural = 'Варианты ответов'
        ordering = ['order']
        # гарантируем, что у вопроса не более одного правильного варианта (опционально)
        constraints = [
            models.UniqueConstraint(
                fields=['question'],
                condition=models.Q(is_correct=True),
                name='unique_correct_choice_per_question'
            )
        ]

    def __str__(self):
        return self.text


class GameSession(models.Model):
    """Игровая сессия (конкретное соревнование)"""
    STATUS_CHOICES = [
        ('prep', 'Подготовка'),
        ('active', 'Активна'),
        ('finished', 'Завершена'),
    ]
    name = models.CharField('Название игры', max_length=200, blank=True)
    start_time = models.DateTimeField('Время начала', null=True, blank=True)
    end_time = models.DateTimeField('Время окончания', null=True, blank=True)
    status = models.CharField('Статус', max_length=10, choices=STATUS_CHOICES, default='prep')
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    # текущий активный вопрос (заполняется во время игры)
    current_game_question = models.ForeignKey('GameQuestion', on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name='+', verbose_name='Текущий вопрос')

    class Meta:
        verbose_name = 'Игровая сессия'
        verbose_name_plural = 'Игровые сессии'

    def __str__(self):
        return self.name or f'Сессия #{self.id}'


class GameQuestion(models.Model):
    """Связь вопроса с игровой сессией (порядковый номер и время старта)"""
    game_session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name='game_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='game_questions')
    order = models.PositiveIntegerField('Порядковый номер вопроса')
    start_time = models.DateTimeField('Время показа вопроса', null=True, blank=True)  # заполняется при старте вопроса

    class Meta:
        verbose_name = 'Вопрос в игре'
        verbose_name_plural = 'Вопросы в игре'
        unique_together = ('game_session', 'order')  # один порядковый номер в сессии
        ordering = ['order']

    def __str__(self):
        return f'{self.game_session} - Вопрос #{self.order}'


class TeamSession(models.Model):
    """Участие команды в конкретной игровой сессии"""
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='sessions')
    game_session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name='teams')
    joined_at = models.DateTimeField('Время присоединения', auto_now_add=True)

    class Meta:
        verbose_name = 'Участие команды'
        verbose_name_plural = 'Участия команд'
        unique_together = ('team', 'game_session')  # команда может участвовать в сессии только один раз

    def __str__(self):
        return f'{self.team} в {self.game_session}'


class Answer(models.Model):
    """Ответ команды на конкретный вопрос в игре"""
    team_session = models.ForeignKey(TeamSession, on_delete=models.CASCADE, related_name='answers',
                                     verbose_name='Команда в сессии')
    game_question = models.ForeignKey(GameQuestion, on_delete=models.CASCADE, related_name='answers',
                                      verbose_name='Вопрос в игре')
    choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True,
                               verbose_name='Выбранный вариант')
    elapsed_time = models.FloatField('Время ответа (сек)', null=True, blank=True)  # от начала показа вопроса
    is_correct = models.BooleanField('Правильный?', default=False)
    answered_at = models.DateTimeField('Время ответа', auto_now_add=True)

    class Meta:
        verbose_name = 'Ответ'
        verbose_name_plural = 'Ответы'
        unique_together = ('team_session', 'game_question')  # одна команда может ответить на вопрос только раз

    def save(self, *args, **kwargs):
        # Автоматически определяем правильность на основе выбранного варианта
        if self.choice:
            self.is_correct = self.choice.is_correct
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.team_session} на вопрос #{self.game_question.order}'