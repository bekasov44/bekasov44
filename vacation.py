import disnake
from disnake.ext import commands, tasks
from disnake import PartialEmoji, Interaction, Message
from datetime import datetime, timedelta, timezone
import json
import os
import asyncio
import re
from typing import Optional, Dict, Any, Set, List, Tuple
import logging

logger = logging.getLogger(__name__)

# Timezone и константы
MSK = timezone(timedelta(hours=3))

# Файлы
VACATION_DATA_FILE = "vacation_data.json"
VACATION_CONFIG_FILE = "vacation_config.json"
VACATION_STATS_FILE = "vacation_stats.json"
VACATION_BUTTONS_FILE = "vacation_buttons.json"
VACATION_THREADS_FILE = "vacation_threads.json"

# Картинки / цвета
IMG_MAIN = "https://i.imgur.com/n8mczeW.png"
IMG_GIF = "https://i.imgur.com/cdE2sAJ.gif"

COLOR_NEUTRAL = 0x404040
COLOR_GREEN = 0x00FF55
COLOR_RED = 0xFF5555
COLOR_BLUE = 0x00BFFF
COLOR_ORANGE = 0xFFA500
COLOR_YELLOW = 0xFFD700

# Эмодзи
BEACH_EMOJI = "🏖️"
CALENDAR_EMOJI = "📅"
CLOCK_EMOJI = "⏰"
PERSON_EMOJI = "👤"
WARNING_EMOJI = "⚠️"
CHECK_EMOJI = "✅"
CROSS_EMOJI = "❌"
PAPER_EMOJI = "📝"
PHONE_EMOJI = "📱"
HOUSE_EMOJI = "🏠"
MENU_EMOJI = "📋"
STATS_EMOJI = "📊"
EXIT_EMOJI = "🚪"
PLANE_EMOJI = "✈️"
LIST_EMOJI = "📜"

# ---------- УТИЛИТНЫЕ ФУНКЦИИ ----------

def ensure_dir_for_file(path: str) -> None:
    """Создание директории для файла"""
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass

def safe_write_json(path: str, data) -> None:
    """Безопасная запись JSON"""
    tmp = f"{path}.tmp"
    try:
        ensure_dir_for_file(path)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        logger.exception(f"Ошибка записи файла {path}")

def load_json(file_path: str, default: dict = None) -> dict:
    """Загрузка JSON файла"""
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            logger.exception(f"Не удалось загрузить {file_path}")
            return default or {}
    return default or {}

def save_json(data: dict, file_path: str) -> None:
    """Сохранение JSON файла"""
    safe_write_json(file_path, data)

# ---------- ЗАГРУЗКА ДАННЫХ ----------

# Загрузка всех данных
vacation_config = load_json(VACATION_CONFIG_FILE, {
    "default": {
        "vacation_role_id": None,
        "review_channel_id": None,
        "list_channel_id": None,
        "log_channel_id": None,
        "allowed_roles": [],
        "banned_roles": [],
        "min_rank_roles": [],
        "max_vacations_per_month": 1,
        "auto_close_hours": 24
    }
})

vacation_data = load_json(VACATION_DATA_FILE, {})
vacation_requests = load_json("vacation_requests.json", {})
vacation_stats = load_json(VACATION_STATS_FILE, {})
vacation_buttons = load_json(VACATION_BUTTONS_FILE, {})
vacation_threads = load_json(VACATION_THREADS_FILE, {})

def parse_date(date_str: str) -> Optional[datetime]:
    """Парсинг даты из формата ДД.ММ.ГГГГ"""
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y").replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=MSK
        )
    except ValueError:
        return None

def format_date(date: datetime) -> str:
    """Форматирование даты"""
    return date.strftime("%d.%m.%Y")

def format_datetime(dt: datetime) -> str:
    """Форматирование даты и времени"""
    return dt.strftime("%d.%m.%Y %H:%M")

def format_duration(days: int) -> str:
    """Форматирование длительности"""
    if days % 10 == 1 and days % 100 != 11:
        return f"{days} день"
    elif 2 <= days % 10 <= 4 and (days % 100 < 10 or days % 100 >= 20):
        return f"{days} дня"
    else:
        return f"{days} дней"

def get_month_key(date: datetime = None) -> str:
    """Получение ключа месяца (YYYY-MM)"""
    if date is None:
        date = datetime.now(MSK)
    return date.strftime("%Y-%m")

def get_config(guild_id: int) -> dict:
    """Получение конфигурации для сервера"""
    guild_id_str = str(guild_id)
    if guild_id_str not in vacation_config:
        vacation_config[guild_id_str] = vacation_config["default"].copy()
        save_json(vacation_config, VACATION_CONFIG_FILE)
    return vacation_config[guild_id_str]

def update_config(guild_id: int, **kwargs) -> None:
    """Обновление конфигурации сервера"""
    config = get_config(guild_id)
    config.update(kwargs)
    save_json(vacation_config, VACATION_CONFIG_FILE)

def can_vote(member: disnake.Member, guild_id: int) -> bool:
    """Проверка прав на голосование"""
    config = get_config(guild_id)
    allowed_roles = config.get("allowed_roles", [])
    return any(role.id in allowed_roles for role in member.roles)

def can_take_vacation(member: disnake.Member, guild_id: int) -> Tuple[bool, str]:
    """Проверка, может ли пользователь брать отпуск"""
    config = get_config(guild_id)
    
    # Проверка запрещенных ролей
    banned_roles = config.get("banned_roles", [])
    if any(role.id in banned_roles for role in member.roles):
        return False, "**`!` Ваша должность не позволяет брать отпуск.**"
    
    # Проверка минимального ранга
    min_rank = config.get("min_rank_roles", [])
    if min_rank and not any(role.id in min_rank for role in member.roles):
        return False, "**`!` Недостаточно высокий ранг для отпуска.**"
    
    # Проверка лимита отпусков в месяц
    user_id = str(member.id)
    month_key = get_month_key()
    
    user_stats = vacation_stats.get(user_id, {})
    month_stats = user_stats.get(month_key, {})
    vacations_taken = month_stats.get("count", 0)
    
    max_per_month = config.get("max_vacations_per_month", 1)
    if vacations_taken >= max_per_month:
        return False, f"**`!` Лимит отпусков на этот месяц исчерпан ({max_per_month}).**"
    
    return True, ""

def update_vacation_stats(user_id: int, duration_days: int, action: str = "taken") -> None:
    """Обновление статистики отпусков"""
    user_id_str = str(user_id)
    month_key = get_month_key()
    
    if user_id_str not in vacation_stats:
        vacation_stats[user_id_str] = {}
    
    if month_key not in vacation_stats[user_id_str]:
        vacation_stats[user_id_str][month_key] = {
            "count": 0,
            "total_days": 0,
            "last_vacation": None
        }
    
    stats = vacation_stats[user_id_str][month_key]
    
    if action == "taken":
        stats["count"] += 1
        stats["total_days"] += duration_days
        stats["last_vacation"] = datetime.now(MSK).isoformat()
    elif action == "cancelled":
        if stats["count"] > 0:
            stats["count"] -= 1
        if stats["total_days"] >= duration_days:
            stats["total_days"] -= duration_days
    
    save_json(vacation_stats, VACATION_STATS_FILE)

def get_user_stats(user_id: int) -> dict:
    """Получение статистики пользователя"""
    user_id_str = str(user_id)
    if user_id_str not in vacation_stats:
        return {"total_vacations": 0, "total_days": 0, "current_month": {"count": 0, "days": 0}}
    
    user_data = vacation_stats[user_id_str]
    total_vacations = sum(month.get("count", 0) for month in user_data.values())
    total_days = sum(month.get("total_days", 0) for month in user_data.values())
    
    current_month = user_data.get(get_month_key(), {"count": 0, "total_days": 0})
    
    return {
        "total_vacations": total_vacations,
        "total_days": total_days,
        "current_month": {
            "count": current_month.get("count", 0),
            "days": current_month.get("total_days", 0)
        }
    }

async def ephemeral_temp(
    inter: Interaction, 
    content: Optional[str] = None, 
    embed: Optional[disnake.Embed] = None, 
    delay: int = 15, 
    view: Optional[disnake.ui.View] = None
) -> None:
    """
    Отправляет ephemeral сообщение и удаляет его через delay секунд.
    """
    try:
        kwargs = {"ephemeral": True}
        if content:
            kwargs["content"] = content
        if embed:
            kwargs["embed"] = embed
        if view:
            kwargs["view"] = view
        
        if not inter.response.is_done():
            await inter.response.send_message(**kwargs)
            msg = await inter.original_response()
        else:
            msg = await inter.followup.send(**kwargs)
        
        # Ждем и удаляем ephemeral сообщение
        if delay > 0:
            await asyncio.sleep(delay)
            try:
                if hasattr(msg, 'delete'):
                    await msg.delete()
                else:
                    await inter.delete_original_response()
            except Exception:
                pass
    except Exception:
        logger.exception("ephemeral_temp failed")

async def send_vacation_log(
    guild: disnake.Guild,
    action: str,
    user: Optional[disnake.Member],
    moderator: Optional[disnake.Member] = None,
    data: Optional[dict] = None
) -> None:
    """Отправка лога в канал"""
    config = get_config(guild.id)
    log_channel_id = config.get("log_channel_id")
    
    if not log_channel_id:
        return
    
    channel = guild.get_channel(int(log_channel_id))
    if not isinstance(channel, disnake.TextChannel):
        return
    
    # Определяем цвет и заголовок по действию
    action_config = {
        "apply": ("📝 Новая заявка", COLOR_ORANGE),
        "approve": ("✅ Заявка одобрена", COLOR_GREEN),
        "deny": ("❌ Заявка отклонена", COLOR_RED),
        "early_return": ("🚪 Досрочный выход", COLOR_YELLOW),
        "auto_close": ("🔒 Автозакрытие", COLOR_NEUTRAL),
        "start": ("🏖️ Начало отпуска", COLOR_BLUE),
        "end": ("🏠 Завершение отпуска", COLOR_BLUE),
        "reminder": ("⏰ Напоминание", COLOR_YELLOW),
        "force_recall": ("⚠️ Принудительный отзыв", COLOR_RED)
    }
    
    title, color = action_config.get(action, ("Действие", COLOR_NEUTRAL))
    
    embed = disnake.Embed(
        title=f"—・{title}",
        color=color,
        timestamp=datetime.now(MSK)
    )
    
    if user:
        embed.add_field(
            name="`👤` Пользователь",
            value=f"{user.mention} | `{user}`",
            inline=True
        )
    
    if moderator:
        embed.add_field(
            name="`👮` Модератор",
            value=f"{moderator.mention} | `{moderator}`",
            inline=True
        )
    
    if data:
        if "start_date" in data and "end_date" in data:
            start = format_date(datetime.fromisoformat(data["start_date"]))
            end = format_date(datetime.fromisoformat(data["end_date"]))
            embed.add_field(
                name="`📅` Период",
                value=f"**{start}** → **{end}**",
                inline=True
            )
        
        if "duration_days" in data:
            embed.add_field(
                name="`⏱️` Длительность",
                value=f"**{format_duration(data['duration_days'])}**",
                inline=True
            )
        
        if "reason" in data:
            embed.add_field(
                name="`📝` Причина",
                value=f"```{data['reason'][:100]}...```",
                inline=False
            )
        
        if "deny_reason" in data:
            embed.add_field(
                name="`❌` Причина отказа",
                value=f"```{data['deny_reason'][:100]}...```",
                inline=False
            )
    
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1369792027390378086/1452244859711656038/a_b43d1c69567168b5acf867cf688c6ce0.gif?ex=69491beb&is=6947ca6b&hm=a0b58914222bd1d72286be7ab3a7b8afdbbd072d31981c7079157a2c20379582&")
    
    try:
        await channel.send(embed=embed)
    except Exception:
        logger.exception("Failed to send vacation log")

# ---------- СИСТЕМА ВЕТКИ ДЛЯ ЗАЯВОК ----------

async def get_or_create_vacation_thread(guild: disnake.Guild, menu_message_id: int) -> Optional[disnake.Thread]:
    """Получение или создание ветки для заявок"""
    guild_id_str = str(guild.id)
    
    # Проверяем, есть ли уже сохраненная ветка
    if guild_id_str in vacation_threads:
        thread_id = vacation_threads[guild_id_str]
        try:
            # Пробуем получить ветку
            thread = guild.get_thread(thread_id)
            if thread and not thread.archived:
                return thread
            
            # Пробуем получить через fetch
            try:
                thread = await guild.fetch_channel(thread_id)
                if isinstance(thread, disnake.Thread) and not thread.archived:
                    return thread
            except:
                pass
        except Exception:
            pass
    
    # Находим канал с сообщением меню
    try:
        channel = None
        menu_message = None
        
        # Ищем сообщение меню по всем каналам
        for ch in guild.text_channels:
            try:
                msg = await ch.fetch_message(menu_message_id)
                menu_message = msg
                channel = ch
                break
            except:
                continue
        
        if not channel or not menu_message:
            logger.error(f"Не удалось найти сообщение меню {menu_message_id} в гильдии {guild.id}")
            return None
        
        # Проверяем, есть ли уже ветка в этом канале
        for thread in channel.threads:
            if thread.name == "📋 Заявки на отпуск" and not thread.archived:
                vacation_threads[guild_id_str] = thread.id
                save_json(vacation_threads, VACATION_THREADS_FILE)
                return thread
        
        # Ищем среди всех активных тредов гильдии
        active_threads = guild.threads
        for thread in active_threads:
            if thread.name == "📋 Заявки на отпуск" and not thread.archived:
                vacation_threads[guild_id_str] = thread.id
                save_json(vacation_threads, VACATION_THREADS_FILE)
                return thread
        
        # Создаем новую ветку в канале
        try:
            thread = await channel.create_thread(
                name="📋 Заявки на отпуск",
                type=disnake.ChannelType.public_thread,
                auto_archive_duration=10080,  # 7 дней
                reason="Ветка для заявок на отпуск"
            )
            
            # Сохраняем ID ветки
            vacation_threads[guild_id_str] = thread.id
            save_json(vacation_threads, VACATION_THREADS_FILE)
            
            # Отправляем приветственное сообщение в ветку
            welcome_embed = disnake.Embed(
                title="📋 Заявки на отпуск",
                description="В этой ветке рассматриваются все заявки на отпуск.\n\n"
                          "**Как работает система:**\n"
                          "1. Пользователь подает заявку через меню\n"
                          "2. Заявка появляется здесь\n"
                          "3. Администраторы рассматривают заявку\n"
                          "4. При одобрении - отпуск добавляется в активные\n"
                          "5. Автоматически выдаются/снимаются роли\n\n"
                          "**Статусы заявок:**\n"
                          "🟡 - На рассмотрении\n"
                          "✅ - Одобрено\n"
                          "❌ - Отклонено",
                color=COLOR_BLUE,
                timestamp=datetime.now(MSK)
            )
            welcome_embed.set_footer(text="Система отпусков")
            await thread.send(embed=welcome_embed)
            
            logger.info(f"Создана новая ветка для заявок: {thread.id} в гильдии {guild.id}")
            return thread
            
        except Exception as e:
            logger.exception(f"Ошибка при создании ветки: {e}")
            return None
            
    except Exception as e:
        logger.exception(f"Ошибка при поиске/создании ветки: {e}")
    
    return None

# ---------- ВЫПАДАЮЩЕЕ МЕНЮ ОТПУСКОВ ----------

class VacationMainMenu(disnake.ui.View):
    """Главное меню отпусков (выпадающий список)"""
    def __init__(self):
        super().__init__(timeout=None)
        
        # Создаем выпадающее меню
        self.select = disnake.ui.Select(
            placeholder=f"{MENU_EMOJI} Меню отпусков",
            options=[
                disnake.SelectOption(
                    label="Подать заявку",
                    description="Заполнить форму на отпуск",
                    emoji="📝",
                    value="apply"
                ),
                disnake.SelectOption(
                    label="Выйти с отпуска",
                    description="Досрочно завершить отпуск",
                    emoji="🚪",
                    value="return"
                ),
                disnake.SelectOption(
                    label="Список отпускников",
                    description="Кто сейчас в отпуске",
                    emoji="📜",
                    value="list"
                ),
                disnake.SelectOption(
                    label="Моя статистика",
                    description="Ваши отпуска и дни",
                    emoji="📊",
                    value="stats"
                )
            ],
            custom_id="vacation_main_menu"
        )
        self.select.callback = self.menu_callback
        self.add_item(self.select)
    
    async def menu_callback(self, inter: disnake.Interaction):
        value = inter.data["values"][0]
        
        if value == "apply":
            await self.apply_vacation(inter)
        elif value == "return":
            await self.return_from_vacation(inter)
        elif value == "list":
            await self.show_vacation_list(inter)
        elif value == "stats":
            await self.show_user_stats(inter)
    
    async def apply_vacation(self, inter: disnake.Interaction):
        """Обработка подачи заявки"""
        can_take, reason = can_take_vacation(inter.author, inter.guild.id)
        if not can_take:
            return await ephemeral_temp(inter, reason, delay=15)
        
        # Показываем модальное окно с выбором даты начала
        await inter.response.send_modal(VacationStartDateModal())
    
    async def return_from_vacation(self, inter: disnake.Interaction):
        """Обработка досрочного выхода"""
        # Ищем активный отпуск пользователя
        user_vacations = []
        for req_id, data in vacation_data.items():
            if (data.get("user_id") == inter.author.id and 
                data.get("status") == "approved"):
                user_vacations.append((req_id, data))
        
        if not user_vacations:
            return await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} У вас нет активного отпуска.**",
                delay=15
            )
        
        # Если несколько активных отпусков, показываем выбор
        if len(user_vacations) > 1:
            view = VacationSelectView(user_vacations, "return")
            await ephemeral_temp(
                inter,
                f"**{WARNING_EMOJI} Выберите отпуск для досрочного завершения:**",
                view=view,
                delay=60
            )
        else:
            request_id, data = user_vacations[0]
            await early_return_vacation(inter, request_id, data)
    
    async def show_vacation_list(self, inter: disnake.Interaction):
        """Показать список активных отпусков"""
        await inter.response.defer(ephemeral=True)
        
        active_vacations = []
        now = datetime.now(MSK)
        
        for req_id, data in vacation_data.items():
            if data.get("status") == "approved":
                end_date = datetime.fromisoformat(data["end_date"])
                if end_date > now:
                    active_vacations.append((req_id, data))
        
        # Сортируем по дате окончания
        active_vacations.sort(key=lambda x: datetime.fromisoformat(x[1]["end_date"]))
        
        # Создаем эмбед
        embed = disnake.Embed(
            title=f"{BEACH_EMOJI} Активные отпуски",
            description=f"**Всего в отпуске: {len(active_vacations)} человек(а)**\n"
                       f"*Обновлено: {format_datetime(now)}*",
            color=COLOR_BLUE,
            timestamp=now
        )
        
        if not active_vacations:
            embed.add_field(
                name=f"{HOUSE_EMOJI} Все дома!",
                value="В данный момент никто не находится в отпуске.",
                inline=False
            )
        else:
            for i, (req_id, data) in enumerate(active_vacations[:15], 1):
                start_date = datetime.fromisoformat(data["start_date"])
                end_date = datetime.fromisoformat(data["end_date"])
                days_left = (end_date.date() - now.date()).days
                
                member = inter.guild.get_member(data["user_id"])
                member_name = member.mention if member else f"`{data['user_name']}`"
                
                # Цвет статуса
                if days_left > 3:
                    status_emoji = "🟢"
                    status_text = f"{days_left} дней осталось"
                elif days_left > 0:
                    status_emoji = "🟡"
                    status_text = f"{days_left} день(дня) осталось"
                else:
                    status_emoji = "🔴"
                    status_text = "Завершается сегодня"
                
                embed.add_field(
                    name=f"{i}. {member_name}",
                    value=f"**{CALENDAR_EMOJI}:** {format_date(start_date)} → {format_date(end_date)}\n"
                          f"**{CLOCK_EMOJI}:** {status_emoji} {status_text}\n"
                          f"**{PAPER_EMOJI}:** {data['reason'][:30]}...",
                    inline=True
                )
        
        embed.set_footer(text="Автоматическое обновление каждые 30 минут")
        embed.set_thumbnail(url=IMG_MAIN)
        
        await ephemeral_temp(inter, embed=embed, delay=60)
    
    async def show_user_stats(self, inter: disnake.Interaction):
        """Показать статистику пользователя"""
        await inter.response.defer(ephemeral=True)
        
        stats = get_user_stats(inter.author.id)
        config = get_config(inter.guild.id)
        max_per_month = config.get("max_vacations_per_month", 1)
        remaining = max_per_month - stats["current_month"]["count"]
        
        embed = disnake.Embed(
            title=f"{STATS_EMOJI} Статистика отпусков",
            color=COLOR_BLUE,
            timestamp=datetime.now(MSK)
        )
        
        embed.add_field(
            name="`👤` Пользователь",
            value=f"{inter.author.mention}\n`{inter.author}`",
            inline=False
        )
        
        embed.add_field(
            name="`📊` Всего отпусков",
            value=f"**{stats['total_vacations']}** заявок",
            inline=True
        )
        
        embed.add_field(
            name="`⏱️` Всего дней",
            value=f"**{stats['total_days']}** дней",
            inline=True
        )
        
        embed.add_field(
            name=f"`{CALENDAR_EMOJI}` Этот месяц",
            value=f"**{stats['current_month']['count']}** отпусков\n"
                  f"**{stats['current_month']['days']}** дней",
            inline=True
        )
        
        embed.add_field(
            name="`📈` Осталось в месяце",
            value=f"**{remaining}** из **{max_per_month}** доступно",
            inline=True
        )
        
        embed.set_thumbnail(url=inter.author.display_avatar.url)
        embed.set_footer(text=f"ID: {inter.author.id}")
        
        await ephemeral_temp(inter, embed=embed, delay=60)

# ---------- МОДАЛЬНЫЕ ОКНА ----------

class VacationStartDateModal(disnake.ui.Modal):
    """Модальное окно для выбора даты начала отпуска"""
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Дата начала отпуска (ДД.ММ.ГГГГ)",
                placeholder="Например: 15.01.2024",
                custom_id="start_date",
                style=disnake.TextInputStyle.short,
                max_length=10,
                min_length=10,
                required=True
            )
        ]
        super().__init__(title="📅 Начало отпуска", components=components)
    
    async def callback(self, inter: disnake.ModalInteraction):
        start_date_str = inter.text_values["start_date"]
        start_date = parse_date(start_date_str)
        
        if not start_date:
            return await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} Неверный формат даты. Используйте ДД.ММ.ГГГГ**",
                delay=15
            )
        
        # Проверка даты (не раньше завтра)
        tomorrow = datetime.now(MSK).date() + timedelta(days=1)
        if start_date.date() < tomorrow:
            return await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} Дата начала должна быть не раньше завтра ({format_date(tomorrow)})**",
                delay=15
            )
        
        # Сохраняем дату начала
        await inter.response.defer(ephemeral=True)
        
        # Показываем выбор длительности
        view = disnake.ui.View(timeout=60)
        
        durations = [
            ("3 дня", 3, "3"),
            ("7 дней", 7, "7"), 
            ("14 дней", 14, "14")
        ]
        
        for label, days, value in durations:
            button = disnake.ui.Button(
                label=label,
                style=disnake.ButtonStyle.secondary,
                custom_id=f"duration_{value}"
            )
            
            async def callback(interaction: disnake.Interaction, d=days, sd=start_date):
                await self.select_duration(interaction, sd, d)
            
            button.callback = callback
            view.add_item(button)
        
        await inter.followup.send(
            f"**{CALENDAR_EMOJI} Выберите длительность отпуска:**\n"
            f"*Начало: {format_date(start_date)}*",
            view=view,
            ephemeral=True
        )
    
    async def select_duration(self, inter: disnake.Interaction, start_date: datetime, duration: int):
        """Обработка выбора длительности"""
        end_date = start_date + timedelta(days=duration)
        
        # Показываем форму для причины
        await inter.response.send_modal(
            VacationReasonModal(start_date, duration, end_date)
        )

class VacationReasonModal(disnake.ui.Modal):
    """Форма для указания причины отпуска"""
    def __init__(self, start_date: datetime, duration: int, end_date: datetime):
        self.start_date = start_date
        self.duration = duration
        self.end_date = end_date
        
        components = [
            disnake.ui.TextInput(
                label="Причина отпуска",
                placeholder="Опишите причину отпуска (максимум 500 символов)",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=True
            ),
            disnake.ui.TextInput(
                label="Контактная информация",
                placeholder="Telegram/WhatsApp или другая связь",
                custom_id="contact",
                style=disnake.TextInputStyle.short,
                max_length=100,
                required=True
            )
        ]
        
        title = f"Отпуск {duration}д • {format_date(start_date)}-{format_date(end_date)}"
        super().__init__(title=title[:45], components=components)
    
    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(ephemeral=True)
        
        reason = inter.text_values["reason"]
        contact = inter.text_values["contact"]
        
        # Создаем заявку
        request_id = f"{inter.author.id}_{int(datetime.now(MSK).timestamp())}"
        
        request_data = {
            "request_id": request_id,
            "user_id": inter.author.id,
            "user_name": str(inter.author),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "duration_days": self.duration,
            "reason": reason,
            "contact": contact,
            "status": "pending",
            "created_at": datetime.now(MSK).isoformat(),
            "guild_id": inter.guild_id,
            "reviewed_by": None,
            "reviewed_at": None,
            "review_comment": None,
            "deny_reason": None,
            "message_id": None,
            "thread_id": None,
            "log_message_id": None,
            "auto_close_at": (datetime.now(MSK) + timedelta(
                hours=get_config(inter.guild_id).get("auto_close_hours", 24)
            )).isoformat(),
            "saved_roles": []
        }
        
        # Сохраняем заявку
        vacation_requests[request_id] = request_data
        save_json(vacation_requests, "vacation_requests.json")
        
        # Получаем конфигурацию сервера
        config = get_config(inter.guild.id)
        
        # Создаем эмбед заявки
        embed = disnake.Embed(
            title=f"Заявка на отпуск | {inter.author.name}",
            description=(
                f"**> Автор:** <@{inter.author.id}>"
                f"\n**{CALENDAR_EMOJI} Период**\n```{format_date(self.start_date)} → {format_date(self.end_date)}```"
                f"\n**{CLOCK_EMOJI} Длительность**\n```{format_duration(self.duration)}```"
                f"\n**{PAPER_EMOJI} Причина**\n```{reason[:500]}```"
                f"\n**{PHONE_EMOJI} Контакты**\n```{contact}```"
            ),
            color=COLOR_ORANGE,
            timestamp=datetime.now(MSK)
        )
        embed.set_footer(text=f"ID {inter.author.id}")
        embed.set_image(url=IMG_GIF)
        
        # Ищем сообщение с меню для этого сервера
        guild_id_str = str(inter.guild.id)
        menu_message_id = None
        if guild_id_str in vacation_buttons and vacation_buttons[guild_id_str]:
            menu_message_id = int(vacation_buttons[guild_id_str][0])
        
        if menu_message_id:
            # Получаем или создаем ветку под сообщением с меню
            thread = await get_or_create_vacation_thread(inter.guild, menu_message_id)
            
            if thread:
                try:
                    # Отправляем заявку в общую ветку
                    view = VacationReviewView(request_id)
                    allowed_roles = config.get("allowed_roles", [])
                    mentions = " ".join([f"<@&{role_id}>" for role_id in allowed_roles])
                    
                    sent_msg = await thread.send(
                        content=f"**{BEACH_EMOJI} Новая заявка на отпуск** {mentions}",
                        embed=embed,
                        view=view
                    )
                    
                    # Сохраняем ID сообщения и ветки
                    request_data["message_id"] = sent_msg.id
                    request_data["thread_id"] = thread.id
                    vacation_requests[request_id] = request_data
                    save_json(vacation_requests, "vacation_requests.json")
                    
                    logger.info(f"Заявка {request_id} отправлена в ветку {thread.id}")
                    
                except Exception as e:
                    logger.exception(f"Ошибка отправки заявки в ветку: {e}")
                    await ephemeral_temp(
                        inter,
                        f"**{CROSS_EMOJI} Ошибка отправки заявки. Попробуйте позже.**",
                        delay=15
                    )
                    return
            else:
                await ephemeral_temp(
                    inter,
                    f"**{CROSS_EMOJI} Не удалось найти ветку для заявок.**",
                    delay=15
                )
                return
        else:
            await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} Меню отпусков не настроено. Обратитесь к администратору.**",
                delay=15
            )
            return
        
        # Логируем
        await send_vacation_log(
            inter.guild,
            "apply",
            inter.author,
            None,
            request_data
        )
        
        # Отправляем подтверждение пользователю
        await ephemeral_temp(
            inter,
            f"**{CHECK_EMOJI} Заявка на отпуск подана!**\n\n"
            f"**{CALENDAR_EMOJI} Период:** {format_date(self.start_date)} - {format_date(self.end_date)}\n"
            f"**{CLOCK_EMOJI} Длительность:** {format_duration(self.duration)}\n"
            f"**{PAPER_EMOJI} Причина:** {reason[:100]}...\n\n"
            f"**Статус заявки:** 🟡 **На рассмотрении**\n"
            f"*Вы получите уведомление в ЛС о решении.*",
            delay=30
        )

class VacationSelectView(disnake.ui.View):
    """View для выбора отпуска"""
    def __init__(self, vacations: list, action: str):
        super().__init__(timeout=60)
        self.vacations = vacations
        self.action = action
        
        options = []
        for req_id, data in vacations:
            end_date = datetime.fromisoformat(data["end_date"])
            days_left = (end_date - datetime.now(MSK)).days
            options.append(
                disnake.SelectOption(
                    label=f"Отпуск до {format_date(end_date)}",
                    description=f"Осталось дней: {days_left}",
                    value=req_id
                )
            )
        
        select = disnake.ui.Select(
            placeholder="Выберите отпуск",
            options=options,
            custom_id="vacation_select"
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, inter: disnake.Interaction):
        request_id = inter.data["values"][0]
        
        # Находим отпуск
        vacation = None
        for req_id, data in self.vacations:
            if req_id == request_id:
                vacation = data
                break
        
        if not vacation:
            return await ephemeral_temp(inter, "❌ Отпуск не найден.", delay=15)
        
        if self.action == "return":
            await early_return_vacation(inter, request_id, vacation)

class VacationApproveModal(disnake.ui.Modal):
    """Модальное окно для одобрения отпуска"""
    def __init__(self, request_id: str):
        self.request_id = request_id
        components = [
            disnake.ui.TextInput(
                label="Комментарий (необязательно)",
                placeholder="Дополнительный комментарий для пользователя",
                custom_id="comment",
                style=disnake.TextInputStyle.paragraph,
                max_length=200,
                required=False
            )
        ]
        super().__init__(title="✅ Одобрение отпуска", components=components)
    
    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(ephemeral=True)
        
        comment = inter.text_values.get("comment", "")
        await approve_vacation(inter, self.request_id, comment)

class VacationDenyModal(disnake.ui.Modal):
    """Модальное окно для отклонения отпуска"""
    def __init__(self, request_id: str):
        self.request_id = request_id
        components = [
            disnake.ui.TextInput(
                label="Причина отказа",
                placeholder="Обязательно укажите причину отклонения",
                custom_id="reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=200,
                required=True
            )
        ]
        super().__init__(title="❌ Отклонение отпуска", components=components)
    
    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(ephemeral=True)
        
        reason = inter.text_values["reason"]
        await deny_vacation(inter, self.request_id, reason)

# ---------- VIEW ДЛЯ РАССМОТРЕНИЯ ЗАЯВОК ----------

class VacationReviewView(disnake.ui.View):
    """View для рассмотрения заявок на отпуск"""
    def __init__(self, request_id: str):
        super().__init__(timeout=None)
        self.request_id = request_id
    
    @disnake.ui.button(
        label="✅ Одобрить",
        style=disnake.ButtonStyle.success,
        emoji="✅",
        custom_id=f"vacation_approve_{datetime.now().timestamp()}"
    )
    async def approve_button(self, button: disnake.ui.Button, inter: disnake.Interaction):
        if not can_vote(inter.author, inter.guild.id):
            return await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} Недостаточно прав.**",
                delay=15
            )
        
        await inter.response.send_modal(VacationApproveModal(self.request_id))
    
    @disnake.ui.button(
        label="❌ Отклонить",
        style=disnake.ButtonStyle.danger,
        emoji="❌",
        custom_id=f"vacation_deny_{datetime.now().timestamp()}"
    )
    async def deny_button(self, button: disnake.ui.Button, inter: disnake.Interaction):
        if not can_vote(inter.author, inter.guild.id):
            return await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} Недостаточно прав.**",
                delay=15
            )
        
        await inter.response.send_modal(VacationDenyModal(self.request_id))

# ---------- ОСНОВНЫЕ ФУНКЦИИ ----------

async def approve_vacation(inter: disnake.Interaction, request_id: str, comment: str = ""):
    """Одобрение отпуска"""
    if request_id not in vacation_requests:
        return await ephemeral_temp(
            inter,
            f"**{CROSS_EMOJI} Заявка не найдена.**",
            delay=15
        )
    
    data = vacation_requests[request_id]
    
    # Проверяем, не одобрена ли уже
    if data["status"] != "pending":
        return await ephemeral_temp(
            inter,
            f"**{CROSS_EMOJI} Заявка уже рассмотрена.**",
            delay=15
        )
    
    # Обновляем данные заявки
    data["status"] = "approved"
    data["reviewed_by"] = inter.author.id
    data["reviewed_at"] = datetime.now(MSK).isoformat()
    data["review_comment"] = comment
    
    # Обновляем статистику
    update_vacation_stats(data["user_id"], data["duration_days"], "taken")
    
    # Добавляем в активные отпуски
    vacation_data[request_id] = data
    save_json(vacation_data, VACATION_DATA_FILE)
    
    # Получаем сообщение с заявкой
    try:
        thread_id = data.get("thread_id")
        message_id = data.get("message_id")
        
        if thread_id and message_id:
            thread = inter.guild.get_thread(int(thread_id))
            if not thread:
                thread = await inter.guild.fetch_channel(int(thread_id))
            
            if thread and isinstance(thread, disnake.Thread):
                message = await thread.fetch_message(int(message_id))
                
                if message:
                    # Создаем новый эмбед с информацией об одобрении
                    new_embed = message.embeds[0]
                    new_embed.color = COLOR_GREEN
                    new_embed.add_field(
                        name=f"{CHECK_EMOJI} Одобрено",
                        value=f"{inter.author.mention}\n{format_datetime(datetime.now(MSK))}",
                        inline=False
                    )
                    
                    if comment:
                        new_embed.add_field(
                            name=f"💬 Комментарий",
                            value=f"```{comment}```",
                            inline=False
                        )
                    
                    # Редактируем сообщение, убираем кнопки
                    await message.edit(embed=new_embed, view=None)
                    
                    # Отправляем второй эмбед с деталями
                    details_embed = disnake.Embed(
                        title="📋 Детали одобрения",
                        description=f"**Заявка на отпуск одобрена**\n\n"
                                  f"**👤 Пользователь:** <@{data['user_id']}>\n"
                                  f"**👮 Модератор:** {inter.author.mention}\n"
                                  f"**📅 Период:** {format_date(datetime.fromisoformat(data['start_date']))} → "
                                  f"{format_date(datetime.fromisoformat(data['end_date']))}\n"
                                  f"**⏱️ Длительность:** {format_duration(data['duration_days'])}\n"
                                  f"**💬 Комментарий:** {comment if comment else 'Нет комментария'}",
                        color=COLOR_GREEN,
                        timestamp=datetime.now(MSK)
                    )
                    details_embed.set_footer(text=f"ID заявки: {request_id}")
                    
                    await message.reply(embed=details_embed)
    except Exception as e:
        logger.exception(f"Ошибка обновления сообщения: {e}")
    
    # Уведомляем пользователя
    user = inter.guild.get_member(data["user_id"])
    if user:
        try:
            embed = disnake.Embed(
                title=f"{CHECK_EMOJI} Ваш отпуск одобрен!",
                description=(
                    f"**Период:** {format_date(datetime.fromisoformat(data['start_date']))} - "
                    f"{format_date(datetime.fromisoformat(data['end_date']))}\n"
                    f"**Длительность:** {format_duration(data['duration_days'])}\n"
                    f"**Рассмотрел:** {inter.author.mention}\n\n"
                    f"**💬 Комментарий:**\n{comment if comment else 'Без комментария'}\n\n"
                    f"*Роль отпуска будет выдана в день начала.*"
                ),
                color=COLOR_GREEN,
                timestamp=datetime.now(MSK)
            )
            embed.set_image(url=IMG_GIF)
            await user.send(embed=embed)
        except Exception:
            pass
    
    # Обновляем список отпусков
    await update_vacation_lists(inter.guild)
    
    # Логируем
    await send_vacation_log(
        inter.guild,
        "approve",
        user,
        inter.author,
        data
    )
    
    await ephemeral_temp(
        inter,
        f"**{CHECK_EMOJI} Отпуск одобрен!**\n"
        f"**Пользователь:** {user.mention if user else 'Не найден'}\n"
        f"**Период:** {format_date(datetime.fromisoformat(data['start_date']))} - "
        f"{format_date(datetime.fromisoformat(data['end_date']))}",
        delay=15
    )

async def deny_vacation(inter: disnake.Interaction, request_id: str, reason: str):
    """Отклонение отпуска"""
    if request_id not in vacation_requests:
        return await ephemeral_temp(
            inter,
            f"**{CROSS_EMOJI} Заявка не найдена.**",
            delay=15
        )
    
    data = vacation_requests[request_id]
    
    # Проверяем, не рассмотрена ли уже
    if data["status"] != "pending":
        return await ephemeral_temp(
            inter,
            f"**{CROSS_EMOJI} Заявка уже рассмотрена.**",
            delay=15
        )
    
    # Обновляем данные заявки
    data["status"] = "denied"
    data["reviewed_by"] = inter.author.id
    data["reviewed_at"] = datetime.now(MSK).isoformat()
    data["deny_reason"] = reason
    
    # Получаем сообщение с заявкой
    try:
        thread_id = data.get("thread_id")
        message_id = data.get("message_id")
        
        if thread_id and message_id:
            thread = inter.guild.get_thread(int(thread_id))
            if not thread:
                thread = await inter.guild.fetch_channel(int(thread_id))
            
            if thread and isinstance(thread, disnake.Thread):
                message = await thread.fetch_message(int(message_id))
                
                if message:
                    # Создаем новый эмбед с информацией об отклонении
                    new_embed = message.embeds[0]
                    new_embed.color = COLOR_RED
                    new_embed.add_field(
                        name=f"{CROSS_EMOJI} Отклонено",
                        value=f"{inter.author.mention}\n{format_datetime(datetime.now(MSK))}",
                        inline=False
                    )
                    
                    # Редактируем сообщение, убираем кнопки
                    await message.edit(embed=new_embed, view=None)
                    
                    # Отправляем второй эмбед с причиной отклонения
                    reason_embed = disnake.Embed(
                        title="📋 Причина отклонения",
                        description=f"**Заявка на отпуск отклонена**\n\n"
                                  f"**👤 Пользователь:** <@{data['user_id']}>\n"
                                  f"**👮 Модератор:** {inter.author.mention}\n"
                                  f"**📅 Период:** {format_date(datetime.fromisoformat(data['start_date']))} → "
                                  f"{format_date(datetime.fromisoformat(data['end_date']))}\n"
                                  f"**⏱️ Длительность:** {format_duration(data['duration_days'])}\n"
                                  f"**📝 Причина отказа:**\n```{reason}```",
                        color=COLOR_RED,
                        timestamp=datetime.now(MSK)
                    )
                    reason_embed.set_footer(text=f"ID заявки: {request_id}")
                    reason_embed.set_image(url=IMG_GIF)
                    
                    await message.reply(embed=reason_embed)
    except Exception as e:
        logger.exception(f"Ошибка обновления сообщения: {e}")
    
    # Уведомляем пользователя
    user = inter.guild.get_member(data["user_id"])
    if user:
        try:
            embed = disnake.Embed(
                title=f"{CROSS_EMOJI} Ваш отпуск отклонен",
                description=(
                    f"**Период:** {format_date(datetime.fromisoformat(data['start_date']))} - "
                    f"{format_date(datetime.fromisoformat(data['end_date']))}\n"
                    f"**Длительность:** {format_duration(data['duration_days'])}\n"
                    f"**Рассмотрел:** {inter.author.mention}\n\n"
                    f"**📝 Причина отказа:**\n{reason}\n\n"
                    f"*Вы можете подать новую заявку, исправив указанные недочеты.*"
                ),
                color=COLOR_RED,
                timestamp=datetime.now(MSK)
            )
            embed.set_image(url=IMG_GIF)
            await user.send(embed=embed)
        except Exception:
            pass
    
    # Логируем
    await send_vacation_log(
        inter.guild,
        "deny",
        user,
        inter.author,
        {**data, "deny_reason": reason}
    )
    
    await ephemeral_temp(
        inter,
        f"**{CROSS_EMOJI} Отпуск отклонен!**\n"
        f"**Пользователь:** {user.mention if user else 'Не найден'}\n"
        f"**Причина:** {reason[:50]}...",
        delay=15
    )

async def early_return_vacation(inter: disnake.Interaction, request_id: str, data: dict):
    """Досрочный выход из отпуска"""
    user = inter.guild.get_member(data["user_id"])
    
    # Снимаем роль отпуска
    config = get_config(inter.guild.id)
    vacation_role_id = config.get("vacation_role_id")
    
    if vacation_role_id and user:
        try:
            vacation_role = inter.guild.get_role(int(vacation_role_id))
            if vacation_role in user.roles:
                await user.remove_roles(vacation_role, reason="Досрочный выход из отпуска")
        except Exception as e:
            logger.exception(f"Ошибка снятия роли отпуска: {e}")
    
    # Восстанавливаем сохраненные роли
    saved_roles = data.get("saved_roles", [])
    if saved_roles and user:
        roles_to_add = []
        for role_id in saved_roles:
            role = inter.guild.get_role(int(role_id))
            if role and role not in user.roles:
                roles_to_add.append(role)
        
        if roles_to_add:
            try:
                await user.add_roles(*roles_to_add, reason="Восстановление ролей после отпуска")
            except Exception as e:
                logger.exception(f"Ошибка восстановления ролей: {e}")
    
    # Обновляем статус отпуска
    data["status"] = "early_return"
    data["early_return_at"] = datetime.now(MSK).isoformat()
    data["early_return_by"] = inter.author.id
    
    # Обновляем статистику
    days_used = (datetime.now(MSK).date() - datetime.fromisoformat(data["start_date"]).date()).days
    if days_used > 0:
        update_vacation_stats(data["user_id"], data["duration_days"] - days_used, "cancelled")
    
    # Обновляем данные
    if request_id in vacation_data:
        del vacation_data[request_id]
        save_json(vacation_data, VACATION_DATA_FILE)
    
    vacation_requests[request_id] = data
    save_json(vacation_requests, "vacation_requests.json")
    
    # Обновляем список отпусков
    await update_vacation_lists(inter.guild)
    
    # Логируем
    await send_vacation_log(
        inter.guild,
        "early_return",
        user,
        inter.author,
        {**data, "days_used": days_used}
    )
    
    # Уведомляем пользователя
    if user and user.id != inter.author.id:
        try:
            embed = disnake.Embed(
                title=f"{HOUSE_EMOJI} Досрочное возвращение",
                description=(
                    f"Ваш отпуск был досрочно завершен {inter.author.mention}.\n"
                    f"**Использовано дней:** {days_used} из {data['duration_days']}\n\n"
                    f"*Все роли восстановлены, роль отпуска снята.*"
                ),
                color=COLOR_BLUE,
                timestamp=datetime.now(MSK)
            )
            embed.set_image(url=IMG_GIF)
            await user.send(embed=embed)
        except Exception:
            pass
    
    await ephemeral_temp(
        inter,
        f"**{CHECK_EMOJI} Отпуск досрочно завершен!**\n"
        f"**Пользователь:** {user.mention if user else 'Не найден'}\n"
        f"**Использовано дней:** {days_used} из {data['duration_days']}",
        delay=15
    )

async def update_vacation_lists(guild: disnake.Guild):
    """Обновление списков отпусков"""
    config = get_config(guild.id)
    list_channel_id = config.get("list_channel_id")
    
    if not list_channel_id:
        return
    
    try:
        list_channel = guild.get_channel(int(list_channel_id))
        if not list_channel:
            return
        
        # Получаем активные отпуски
        active_vacations = []
        now = datetime.now(MSK)
        
        for req_id, data in vacation_data.items():
            if data.get("status") == "approved":
                end_date = datetime.fromisoformat(data["end_date"])
                if end_date > now:
                    active_vacations.append((req_id, data))
        
        # Сортируем по дате окончания
        active_vacations.sort(key=lambda x: datetime.fromisoformat(x[1]["end_date"]))
        
        # Создаем эмбед
        embed = disnake.Embed(
            title=f"{BEACH_EMOJI} Активные отпуски",
            description=f"**Всего в отпуске: {len(active_vacations)} человек(а)**\n"
                       f"*Обновлено: {format_datetime(now)}*",
            color=COLOR_BLUE,
            timestamp=now
        )
        
        if not active_vacations:
            embed.add_field(
                name=f"{HOUSE_EMOJI} Все дома!",
                value="В данный момент никто не находится в отпуске.",
                inline=False
            )
        else:
            for i, (req_id, data) in enumerate(active_vacations[:15], 1):
                start_date = datetime.fromisoformat(data["start_date"])
                end_date = datetime.fromisoformat(data["end_date"])
                days_left = (end_date.date() - now.date()).days
                
                member = guild.get_member(data["user_id"])
                member_name = member.mention if member else f"`{data['user_name']}`"
                
                # Цвет статуса
                if days_left > 3:
                    status_emoji = "🟢"
                    status_text = f"{days_left} дней осталось"
                elif days_left > 0:
                    status_emoji = "🟡"
                    status_text = f"{days_left} день(дня) осталось"
                else:
                    status_emoji = "🔴"
                    status_text = "Завершается сегодня"
                
                embed.add_field(
                    name=f"{i}. {member_name}",
                    value=f"**{CALENDAR_EMOJI}:** {format_date(start_date)} → {format_date(end_date)}\n"
                          f"**{CLOCK_EMOJI}:** {status_emoji} {status_text}\n"
                          f"**{PAPER_EMOJI}:** {data['reason'][:30]}...",
                    inline=True
                )
        
        embed.set_footer(text="Автоматическое обновление каждые 30 минут")
        embed.set_thumbnail(url=IMG_MAIN)
        
        # Ищем существующее сообщение
        async for message in list_channel.history(limit=50):
            if message.author.id == guild.me.id and message.embeds:
                await message.edit(embed=embed)
                return
        
        # Если сообщение не найдено, создаем новое
        await list_channel.send(embed=embed)
        
    except Exception as e:
        logger.exception(f"Ошибка обновления списка: {e}")

# ---------- ЗАДАЧИ ----------

class VacationTasks(commands.Cog):
    """Задачи для автоматизации отпусков"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_vacations.start()
        self.check_reminders.start()
        self.check_auto_close.start()
    
    def cog_unload(self):
        self.check_vacations.cancel()
        self.check_reminders.cancel()
        self.check_auto_close.cancel()
    
    @tasks.loop(minutes=30)
    async def check_vacations(self):
        """Проверка начала/окончания отпусков"""
        for guild in self.bot.guilds:
            config = get_config(guild.id)
            
            # Проверяем активные отпуски
            now = datetime.now(MSK)
            
            for request_id, data in list(vacation_data.items()):
                if data.get("status") != "approved":
                    continue
                
                start_date = datetime.fromisoformat(data["start_date"])
                end_date = datetime.fromisoformat(data["end_date"])
                vacation_role_id = config.get("vacation_role_id")
                
                # Начало отпуска (сегодня)
                if start_date.date() == now.date():
                    user = guild.get_member(data["user_id"])
                    if user and vacation_role_id:
                        try:
                            vacation_role = guild.get_role(int(vacation_role_id))
                            if vacation_role and vacation_role not in user.roles:
                                # Сохраняем текущие роли
                                saved_roles = []
                                for role in user.roles:
                                    if role.id != int(vacation_role_id) and not role.managed:
                                        saved_roles.append(role.id)
                                
                                data["saved_roles"] = saved_roles
                                
                                # Выдаем роль отпуска
                                await user.add_roles(vacation_role, reason="Начало отпуска")
                                
                                # Уведомляем пользователя
                                try:
                                    embed = disnake.Embed(
                                        title=f"{PLANE_EMOJI} Ваш отпуск начался!",
                                        description=(
                                            f"С сегодняшнего дня вы официально в отпуске!\n\n"
                                            f"**Период:** {format_date(start_date)} - {format_date(end_date)}\n"
                                            f"**Длительность:** {format_duration(data['duration_days'])}\n\n"
                                            f"*Хорошего отдыха! Роль отпуска выдана.*"
                                        ),
                                        color=COLOR_GREEN,
                                        timestamp=datetime.now(MSK)
                                    )
                                    embed.set_image(url=IMG_GIF)
                                    await user.send(embed=embed)
                                except Exception:
                                    pass
                                
                                # Логируем
                                await send_vacation_log(
                                    guild,
                                    "start",
                                    user,
                                    None,
                                    data
                                )
                                
                                # Обновляем данные
                                vacation_data[request_id] = data
                                save_json(vacation_data, VACATION_DATA_FILE)
                                
                        except Exception as e:
                            logger.exception(f"Ошибка выдачи роли отпуска: {e}")
                
                # Окончание отпуска (сегодня или в прошлом)
                elif end_date.date() <= now.date():
                    user = guild.get_member(data["user_id"])
                    
                    # Снимаем роль отпуска
                    if user and vacation_role_id:
                        try:
                            vacation_role = guild.get_role(int(vacation_role_id))
                            if vacation_role in user.roles:
                                await user.remove_roles(vacation_role, reason="Окончание отпуска")
                        except Exception as e:
                            logger.exception(f"Ошибка снятия роли отпуска: {e}")
                    
                    # Восстанавливаем роли
                    saved_roles = data.get("saved_roles", [])
                    if saved_roles and user:
                        roles_to_add = []
                        for role_id in saved_roles:
                            role = guild.get_role(int(role_id))
                            if role and role not in user.roles:
                                roles_to_add.append(role)
                        
                        if roles_to_add:
                            try:
                                await user.add_roles(*roles_to_add, reason="Восстановление ролей после отпуска")
                            except Exception as e:
                                logger.exception(f"Ошибка восстановления ролей: {e}")
                    
                    # Уведомляем пользователя
                    if user:
                        try:
                            embed = disnake.Embed(
                                title=f"{HOUSE_EMOJI} Ваш отпуск завершен!",
                                description=(
                                    f"Ваш отпуск подошел к концу. Добро пожаловать обратно!\n\n"
                                    f"**Период:** {format_date(start_date)} - {format_date(end_date)}\n"
                                    f"**Длительность:** {format_duration(data['duration_days'])}\n\n"
                                    f"*Все роли восстановлены, роль отпуска снята.*"
                                ),
                                color=COLOR_BLUE,
                                timestamp=datetime.now(MSK)
                            )
                            embed.set_image(url=IMG_GIF)
                            await user.send(embed=embed)
                        except Exception:
                            pass
                    
                    # Обновляем статус
                    data["status"] = "completed"
                    
                    # Удаляем из активных
                    if request_id in vacation_data:
                        del vacation_data[request_id]
                    
                    # Сохраняем в запросах
                    vacation_requests[request_id] = data
                    
                    # Логируем
                    await send_vacation_log(
                        guild,
                        "end",
                        user,
                        None,
                        data
                    )
            
            # Сохраняем данные
            save_json(vacation_data, VACATION_DATA_FILE)
            save_json(vacation_requests, "vacation_requests.json")
            
            # Обновляем списки
            await update_vacation_lists(guild)
    
    @tasks.loop(hours=1)
    async def check_reminders(self):
        """Проверка напоминаний за 1 день до окончания"""
        now = datetime.now(MSK)
        
        for guild in self.bot.guilds:
            for request_id, data in vacation_data.items():
                if data.get("status") != "approved":
                    continue
                
                end_date = datetime.fromisoformat(data["end_date"])
                days_left = (end_date.date() - now.date()).days
                
                # Напоминание за 1 день
                if days_left == 1 and not data.get("reminder_sent"):
                    user = guild.get_member(data["user_id"])
                    if user:
                        try:
                            embed = disnake.Embed(
                                title=f"{CLOCK_EMOJI} Напоминание об отпуске",
                                description=(
                                    f"Завтра заканчивается ваш отпуск!\n\n"
                                    f"**Период:** {format_date(datetime.fromisoformat(data['start_date']))} - "
                                    f"{format_date(end_date)}\n"
                                    f"**Осталось:** 1 день\n\n"
                                    f"*Готовьтесь к возвращению!*"
                                ),
                                color=COLOR_YELLOW,
                                timestamp=datetime.now(MSK)
                            )
                            embed.set_image(url=IMG_GIF)
                            await user.send(embed=embed)
                            
                            # Отмечаем, что напоминание отправлено
                            data["reminder_sent"] = True
                            vacation_data[request_id] = data
                            
                            # Логируем
                            await send_vacation_log(
                                guild,
                                "reminder",
                                user,
                                None,
                                data
                            )
                            
                        except Exception:
                            pass
    
    @tasks.loop(minutes=15)
    async def check_auto_close(self):
        """Автоматическое закрытие просроченных заявок"""
        now = datetime.now(MSK)
        
        for guild in self.bot.guilds:
            config = get_config(guild.id)
            auto_close_hours = config.get("auto_close_hours", 24)
            
            for request_id, data in list(vacation_requests.items()):
                if data.get("status") != "pending":
                    continue
                
                # Проверяем время создания заявки
                created_at = datetime.fromisoformat(data["created_at"])
                auto_close_at = created_at + timedelta(hours=auto_close_hours)
                
                if now >= auto_close_at:
                    # Автоматически закрываем заявку
                    data["status"] = "cancelled"
                    data["auto_closed"] = True
                    data["auto_closed_at"] = now.isoformat()
                    
                    # Обновляем сообщение с заявкой
                    message_id = data.get("message_id")
                    thread_id = data.get("thread_id")
                    if message_id and thread_id:
                        try:
                            thread = guild.get_thread(int(thread_id))
                            if not thread:
                                thread = await guild.fetch_channel(int(thread_id))
                            
                            if thread and isinstance(thread, disnake.Thread):
                                message = await thread.fetch_message(int(message_id))
                                if message:
                                    embed = message.embeds[0]
                                    embed.color = COLOR_NEUTRAL
                                    embed.add_field(
                                        name="🔒 Автозакрытие",
                                        value=f"Заявка автоматически закрыта через {auto_close_hours}ч\n"
                                              f"{format_datetime(now)}",
                                        inline=False
                                    )
                                    await message.edit(embed=embed, view=None)
                        except Exception:
                            pass
                    
                    # Обновляем данные
                    vacation_requests[request_id] = data
                    
                    # Логируем
                    await send_vacation_log(
                        guild,
                        "auto_close",
                        None,
                        None,
                        data
                    )
            
            # Сохраняем данные
            save_json(vacation_requests, "vacation_requests.json")
    
    @check_vacations.before_loop
    @check_reminders.before_loop
    @check_auto_close.before_loop
    async def before_tasks(self):
        await self.bot.wait_until_ready()

# ---------- КОМАНДЫ АДМИНИСТРАЦИИ ----------

class VacationAdmin(commands.Cog):
    """Команды администрации для управления отпусками"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.slash_command(name="отпуски", description="Управление системой отпусков")
    @commands.has_permissions(administrator=True)
    async def vacation_admin(self, inter: disnake.ApplicationCommandInteraction):
        pass
    
    @vacation_admin.sub_command(name="настройка", description="Настройка системы отпусков")
    async def vacation_setup(
        self,
        inter: disnake.ApplicationCommandInteraction,
        канал_заявок: disnake.TextChannel = commands.Param(description="Канал для создания веток с заявками"),
        канал_списка: disnake.TextChannel = commands.Param(description="Канал для списка активных отпусков"),
        канал_логов: disnake.TextChannel = commands.Param(description="Канал для логов", default=None),
        роль_отпуска: disnake.Role = commands.Param(description="Роль 'В отпуске'"),
        автозакрытие: int = commands.Param(description="Часы до автозакрытия заявки", default=24, choices=[12, 24, 48, 72]),
        лимит_в_месяц: int = commands.Param(description="Макс отпусков в месяц на человека", default=1, choices=[1, 2, 3])
    ):
        await inter.response.defer(ephemeral=True)
        
        # Сохраняем конфигурацию
        update_config(
            inter.guild.id,
            review_channel_id=канал_заявок.id,
            list_channel_id=канал_списка.id,
            log_channel_id=канал_логов.id if канал_логов else None,
            vacation_role_id=роль_отпуска.id,
            auto_close_hours=автозакрытие,
            max_vacations_per_month=лимит_в_месяц
        )
        
        embed = disnake.Embed(
            title=f"{CHECK_EMOJI} Настройка завершена!",
            color=COLOR_GREEN,
            timestamp=datetime.now(MSK)
        )
        
        embed.add_field(
            name="`📝` Канал заявок",
            value=канал_заявок.mention,
            inline=True
        )
        
        embed.add_field(
            name="`📜` Канал списка",
            value=канал_списка.mention,
            inline=True
        )
        
        embed.add_field(
            name="`📋` Канал логов",
            value=канал_логов.mention if канал_логов else "Не указан",
            inline=True
        )
        
        embed.add_field(
            name="`🎭` Роль отпуска",
            value=роль_отпуска.mention,
            inline=True
        )
        
        embed.add_field(
            name="`⏰` Автозакрытие",
            value=f"{автозакрытие} часов",
            inline=True
        )
        
        embed.add_field(
            name="`📊` Лимит в месяц",
            value=f"{лимит_в_месяц} отпуск(а)",
            inline=True
        )
        
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1369792027390378086/1452244859711656038/a_b43d1c69567168b5acf867cf688c6ce0.gif?ex=69491beb&is=6947ca6b&hm=a0b58914222bd1d72286be7ab3a7b8afdbbd072d31981c7079157a2c20379582&")
        
        await ephemeral_temp(inter, embed=embed, delay=30)
    
    @vacation_admin.sub_command(name="роли", description="Настройка ролей для системы отпусков")
    async def vacation_roles(
        self,
        inter: disnake.ApplicationCommandInteraction,
        голосующие_роли: str = commands.Param(description="ID ролей для голосования через пробел", default=""),
        запрещенные_роли: str = commands.Param(description="ID ролей, которым запрещен отпуск", default=""),
        минимальный_ранг: str = commands.Param(description="ID ролей минимального ранга", default="")
    ):
        await inter.response.defer(ephemeral=True)
        
        # Парсим ID ролей
        def parse_role_ids(ids_str: str) -> List[int]:
            if not ids_str:
                return []
            return [int(rid) for rid in ids_str.split() if rid.isdigit()]
        
        allowed_roles = parse_role_ids(голосующие_роли)
        banned_roles = parse_role_ids(запрещенные_роли)
        min_rank_roles = parse_role_ids(минимальный_ранг)
        
        # Сохраняем конфигурацию
        update_config(
            inter.guild.id,
            allowed_roles=allowed_roles,
            banned_roles=banned_roles,
            min_rank_roles=min_rank_roles
        )
        
        # Получаем объекты ролей для отображения
        def get_role_mentions(role_ids: List[int]) -> str:
            if not role_ids:
                return "Не настроено"
            return " ".join(f"<@&{rid}>" for rid in role_ids)
        
        embed = disnake.Embed(
            title=f"{CHECK_EMOJI} Роли настроены!",
            color=COLOR_GREEN,
            timestamp=datetime.now(MSK)
        )
        
        embed.add_field(
            name="`👮` Роли для голосования",
            value=get_role_mentions(allowed_roles),
            inline=False
        )
        
        embed.add_field(
            name="`🚫` Запрещенные роли",
            value=get_role_mentions(banned_roles),
            inline=True
        )
        
        embed.add_field(
            name="`📈` Минимальный ранг",
            value=get_role_mentions(min_rank_roles),
            inline=True
        )
        
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1369792027390378086/1452244859711656038/a_b43d1c69567168b5acf867cf688c6ce0.gif?ex=69491beb&is=6947ca6b&hm=a0b58914222bd1d72286be7ab3a7b8afdbbd072d31981c7079157a2c20379582&")
        
        await ephemeral_temp(inter, embed=embed, delay=30)
    
    @vacation_admin.sub_command(name="кнопка", description="Разместить меню для системы отпусков")
    async def vacation_button_cmd(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        
        config = get_config(inter.guild.id)
        
        if not config.get("review_channel_id"):
            return await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} Сначала настройте систему командой `/отпуски настройка`**",
                delay=15
            )
        
        embed = disnake.Embed(
            title=f"{BEACH_EMOJI} Система отпусков",
            description=(
                f"**Подача заявки на отпуск**\n\n"
                f"**📋 Доступные периоды:**\n"
                f"• 3 дня\n• 7 дней\n• 14 дней\n\n"
                f"**⚙️ Условия:**\n"
                f"• Заявка подается заранее\n"
                f"• Максимум **{config.get('max_vacations_per_month', 1)}** отпуск(а) в месяц\n"
                f"• Отпуск можно завершить досрочно\n"
                f"• Роли сохраняются и восстанавливаются автоматически\n\n"
                f"**📝 Как подать заявку:**\n"
                f"1. Выберите в меню ниже 'Подать заявку'\n"
                f"2. Выберите дату начала и длительность\n"
                f"3. Укажите причину и контакты\n"
                f"4. Ожидайте решения\n\n"
                f"*Заявки рассматриваются в течение {config.get('auto_close_hours', 24)} часов*"
            ),
            color=COLOR_BLUE,
            timestamp=datetime.now(MSK)
        )
        
        embed.add_field(
            name="🔄 Автоматизация",
            value="• Роль отпуска выдается автоматически\n"
                 "• Напоминание за 1 день до окончания\n"
                 "• Автовосстановление ролей",
            inline=True
        )
        
        embed.add_field(
            name="📊 Статистика",
            value="• Отслеживание всех отпусков\n"
                 "• Лимиты и ограничения\n"
                 "• Подробные логи",
            inline=True
        )
        
        embed.set_thumbnail(url=IMG_MAIN)
        embed.set_footer(text="Хорошего отдыха! 🏖️")
        
        # Отправляем меню
        apply_channel = inter.guild.get_channel(int(config["review_channel_id"]))
        if apply_channel:
            try:
                message = await apply_channel.send(embed=embed, view=VacationMainMenu())
                
                # Сохраняем ID сообщения с кнопкой
                guild_id_str = str(inter.guild_id)
                if guild_id_str not in vacation_buttons:
                    vacation_buttons[guild_id_str] = []
                
                if str(message.id) not in vacation_buttons[guild_id_str]:
                    vacation_buttons[guild_id_str].append(str(message.id))
                    save_json(vacation_buttons, VACATION_BUTTONS_FILE)
                
                await ephemeral_temp(
                    inter,
                    f"**{CHECK_EMOJI} Меню отпусков успешно размещено в {apply_channel.mention}!**",
                    delay=15
                )
            except Exception as e:
                await ephemeral_temp(
                    inter,
                    f"**{CROSS_EMOJI} Ошибка: {str(e)[:100]}**",
                    delay=15
                )
        else:
            await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} Канал для заявок не найден.**",
                delay=15
            )
    
    @vacation_admin.sub_command(name="статистика", description="Статистика по отпускам")
    async def vacation_stats_cmd(
        self,
        inter: disnake.ApplicationCommandInteraction,
        пользователь: disnake.Member = commands.Param(description="Пользователь для статистики", default=None)
    ):
        await inter.response.defer(ephemeral=False)
        
        if пользователь:
            # Статистика конкретного пользователя
            stats = get_user_stats(пользователь.id)
            config = get_config(inter.guild.id)
            max_per_month = config.get("max_vacations_per_month", 1)
            remaining = max_per_month - stats["current_month"]["count"]
            
            embed = disnake.Embed(
                title=f"{STATS_EMOJI} Статистика отпусков",
                color=COLOR_BLUE,
                timestamp=datetime.now(MSK)
            )
            
            embed.add_field(
                name="`👤` Пользователь",
                value=f"{пользователь.mention}\n`{пользователь}`",
                inline=False
            )
            
            embed.add_field(
                name="`📊` Всего отпусков",
                value=f"**{stats['total_vacations']}** заявок",
                inline=True
            )
            
            embed.add_field(
                name="`⏱️` Всего дней",
                value=f"**{stats['total_days']}** дней",
                inline=True
            )
            
            embed.add_field(
                name=f"`{CALENDAR_EMOJI}` Этот месяц",
                value=f"**{stats['current_month']['count']}** отпусков\n"
                      f"**{stats['current_month']['days']}** дней",
                inline=True
            )
            
            embed.add_field(
                name="`📈` Осталось в месяце",
                value=f"**{remaining}** из **{max_per_month}** доступно",
                inline=True
            )
            
            embed.set_thumbnail(url=пользователь.display_avatar.url)
            embed.set_footer(text=f"ID: {пользователь.id}")
            
            await inter.edit_original_response(embed=embed)
            return
        
        # Общая статистика
        month_key = get_month_key()
        
        # Собираем статистику
        total_vacations = 0
        total_days = 0
        active_vacations = 0
        users_this_month = set()
        
        for user_id_str, user_data in vacation_stats.items():
            if month_key in user_data:
                month_data = user_data[month_key]
                total_vacations += month_data.get("count", 0)
                total_days += month_data.get("total_days", 0)
                users_this_month.add(user_id_str)
        
        # Активные отпуски
        now = datetime.now(MSK)
        for req_id, data in vacation_data.items():
            if data.get("status") == "approved":
                end_date = datetime.fromisoformat(data["end_date"])
                if end_date > now:
                    active_vacations += 1
        
        embed = disnake.Embed(
            title=f"{BEACH_EMOJI} Статистика отпусков",
            description=(
                f"**Месяц:** {month_key}\n"
                f"**Всего пользователей:** {len(users_this_month)}\n"
                f"**Всего отпусков:** {total_vacations}\n"
                f"**Всего дней:** {total_days}\n"
                f"**Активных отпусков:** {active_vacations}"
            ),
            color=COLOR_BLUE,
            timestamp=datetime.now(MSK)
        )
        
        # Топ пользователей по количеству отпусков
        top_users = []
        for user_id_str in users_this_month:
            user_data = vacation_stats[user_id_str]
            month_data = user_data.get(month_key, {})
            top_users.append((user_id_str, month_data.get("count", 0), month_data.get("total_days", 0)))
        
        top_users.sort(key=lambda x: x[1], reverse=True)
        
        if top_users:
            top_text = ""
            for i, (user_id, count, days) in enumerate(top_users[:5], 1):
                member = inter.guild.get_member(int(user_id))
                name = member.mention if member else f"`ID: {user_id}`"
                top_text += f"{i}. {name} - {count} отпусков ({days} дней)\n"
            
            embed.add_field(name="🏆 Топ пользователей", value=top_text, inline=False)
        
        embed.set_thumbnail(url=IMG_MAIN)
        embed.set_footer(text=f"ID сервера: {inter.guild.id}")
        
        await inter.edit_original_response(embed=embed)
    
    @vacation_admin.sub_command(name="принудительно", description="Принудительные действия с отпуском")
    async def vacation_force(
        self,
        inter: disnake.ApplicationCommandInteraction,
        действие: str = commands.Param(description="Действие", choices=["завершить", "отозвать"]),
        пользователь: disnake.Member = commands.Param(description="Пользователь")
    ):
        await inter.response.defer(ephemeral=True)
        
        # Поиск активного отпуска пользователя
        active_vacation = None
        for req_id, data in vacation_data.items():
            if (data.get("user_id") == пользователь.id and 
                data.get("status") == "approved"):
                active_vacation = (req_id, data)
                break
        
        if not active_vacation:
            return await ephemeral_temp(
                inter,
                f"**{CROSS_EMOJI} У {пользователь.mention} нет активного отпуска.**",
                delay=15
            )
        
        request_id, data = active_vacation
        
        if действие == "завершить":
            # Завершаем отпуск как обычно
            await early_return_vacation(inter, request_id, data)
            
            await ephemeral_temp(
                inter,
                f"**{CHECK_EMOJI} Отпуск {пользователь.mention} принудительно завершен.**",
                delay=15
            )
        
        elif действие == "отозвать":
            # Отзываем одобрение (если отпуск еще не начался)
            start_date = datetime.fromisoformat(data["start_date"])
            now = datetime.now(MSK)
            
            if start_date.date() <= now.date():
                return await ephemeral_temp(
                    inter,
                    f"**{CROSS_EMOJI} Нельзя отозвать начавшийся отпуск. Используйте 'завершить'.**",
                    delay=15
                )
            
            # Меняем статус на отклоненный
            data["status"] = "denied"
            data["force_recalled"] = True
            data["force_recalled_by"] = inter.author.id
            data["force_recalled_at"] = now.isoformat()
            
            # Обновляем сообщение с заявкой
            message_id = data.get("message_id")
            thread_id = data.get("thread_id")
            if message_id and thread_id:
                try:
                    thread = inter.guild.get_thread(int(thread_id))
                    if not thread:
                        thread = await inter.guild.fetch_channel(int(thread_id))
                    
                    if thread and isinstance(thread, disnake.Thread):
                        message = await thread.fetch_message(int(message_id))
                        if message:
                            embed = message.embeds[0]
                            embed.color = COLOR_RED
                            embed.add_field(
                                name=f"{CROSS_EMOJI} Отозвано администратором",
                                value=f"{inter.author.mention}\n{format_datetime(now)}",
                                inline=False
                            )
                            await message.edit(embed=embed, view=None)
                            
                            # Отправляем второй эмбед с причиной
                            reason_embed = disnake.Embed(
                                title="📋 Причина отзыва",
                                description=f"**Одобренный отпуск отозван администратором**\n\n"
                                          f"**👤 Пользователь:** {пользователь.mention}\n"
                                          f"**👮 Администратор:** {inter.author.mention}\n"
                                          f"**📅 Период:** {format_date(start_date)} → "
                                          f"{format_date(datetime.fromisoformat(data['end_date']))}\n"
                                          f"**⚠️ Причина:** Принудительный отзыв администратором",
                                color=COLOR_RED,
                                timestamp=datetime.now(MSK)
                            )
                            reason_embed.set_image(url=IMG_GIF)
                            await message.reply(embed=reason_embed)
                except Exception:
                    pass
            
            # Уведомляем пользователя
            try:
                embed = disnake.Embed(
                    title=f"{CROSS_EMOJI} Отпуск отозван",
                    description=(
                        f"Ваш одобренный отпуск был отозван администратором {inter.author.mention}.\n\n"
                        f"**Период:** {format_date(start_date)} - "
                        f"{format_date(datetime.fromisoformat(data['end_date']))}\n\n"
                        f"*Для уточнения причин обратитесь к администрации.*"
                    ),
                    color=COLOR_RED,
                    timestamp=datetime.now(MSK)
                )
                embed.set_image(url=IMG_GIF)
                await пользователь.send(embed=embed)
            except Exception:
                pass
            
            # Обновляем данные
            vacation_requests[request_id] = data
            if request_id in vacation_data:
                del vacation_data[request_id]
            
            save_json(vacation_data, VACATION_DATA_FILE)
            save_json(vacation_requests, "vacation_requests.json")
            
            # Обновляем статистику
            update_vacation_stats(data["user_id"], data["duration_days"], "cancelled")
            
            # Обновляем списки
            await update_vacation_lists(inter.guild)
            
            # Логируем
            await send_vacation_log(
                inter.guild,
                "force_recall",
                пользователь,
                inter.author,
                {**data, "note": "Принудительный отзыв администратором"}
            )
            
            await ephemeral_temp(
                inter,
                f"**{CHECK_EMOJI} Отпуск {пользователь.mention} успешно отозван.**",
                delay=15
            )

# ---------- ОСНОВНОЙ КОГ ----------

class VacationSystem(commands.Cog):
    """Основной ког системы отпусков"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def cog_load(self):
        """Загрузка персистентных view"""
        self.bot.add_view(VacationMainMenu())
        self.bot.add_view(VacationReviewView("dummy"))
        
        # Загружаем кнопки
        for guild_id_str, message_ids in vacation_buttons.items():
            guild = self.bot.get_guild(int(guild_id_str))
            if not guild:
                continue
            
            for message_id in message_ids:
                try:
                    # Ищем сообщение по всем каналам
                    for channel in guild.text_channels:
                        try:
                            msg = await channel.fetch_message(int(message_id))
                            await msg.edit(view=VacationMainMenu())
                            break
                        except Exception:
                            continue
                except Exception:
                    pass
    
    @commands.Cog.listener()
    async def on_message_delete(self, message: disnake.Message):
        """Удаление информации о кнопке при удалении сообщения"""
        if not message.guild:
            return
        
        guild_id_str = str(message.guild.id)
        if guild_id_str in vacation_buttons and str(message.id) in vacation_buttons[guild_id_str]:
            vacation_buttons[guild_id_str].remove(str(message.id))
            save_json(vacation_buttons, VACATION_BUTTONS_FILE)
            
        # Если удалили сообщение с меню, удаляем и информацию о ветке
        if guild_id_str in vacation_threads:
            del vacation_threads[guild_id_str]
            save_json(vacation_threads, VACATION_THREADS_FILE)

# ---------- НАСТРОЙКА БОТА ----------

def setup(bot: commands.Bot):
    bot.add_cog(VacationSystem(bot))
    bot.add_cog(VacationTasks(bot))
    bot.add_cog(VacationAdmin(bot))
