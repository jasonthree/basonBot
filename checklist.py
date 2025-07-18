import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from discord import app_commands
import json
import os
from datetime import datetime, timedelta
from typing import Optional
import random


TOKEN = os.getenv("DISCORD_TOKEN")
FILENAME = "user_checklists.json"


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Load/Save Checklist Data
def load_data():
    if os.path.exists(FILENAME):
        with open(FILENAME, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(FILENAME, "w") as f:
        json.dump(data, f, indent=2)

data = load_data()

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")
    reminder_loop.start()

# Background task for reminders
@tasks.loop(seconds=60)
async def reminder_loop():
    now = datetime.now()
    for user_id, task_list in data.items():
        if not isinstance(task_list, list):
            continue
        for task in task_list:
            if not isinstance(task, dict):
                continue
            if task.get('done'):
                continue
            due_str = task.get('due')
            if not due_str:
                continue
            try:
                due = datetime.strptime(due_str, "%Y-%m-%d %I:%M %p")
                if now <= due <= now + timedelta(minutes=15):
                    user = await bot.fetch_user(int(user_id))
                    await user.send(f"🔔 Reminder: '{task['task']}' is due at {task['due']} (Priority: {task['priority']})")
            except ValueError:
                continue

# Slash command to view checklist
@tree.command(name="checklist", description="View your checklist sorted by priority and due date")
async def slash_checklist(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    tasks = data.get(user_id, [])

    if not tasks:
        await interaction.response.send_message("You don’t have any tasks. Use `/add` to start.")
        return

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    tasks.sort(key=lambda x: (priority_order.get(x.get("priority"), 3), x.get("due", "9999-12-31 11:59 PM")))

    view = TaskButtonsView(user_id, tasks)
    task_list = "\n".join(
        f"{i+1}. {'✅' if t.get('done') else '❌'} {t.get('task')} | {t.get('priority')} | {t.get('due', 'No due date')}" for i, t in enumerate(tasks)
    )
    await interaction.response.send_message(f"**Your Checklist:**\n{task_list}", view=view)

# Slash command to add task
@tree.command(name="add", description="Add a new task with optional priority and due date")
@app_commands.describe(
    due_date="Optional due date in YYYY-MM-DD format",
    due_time="Optional due time in HH:MM AM/PM format"
)
async def slash_add(
    interaction: discord.Interaction,
    task: str,
    priority: str,
    *,
    due_date: Optional[str] = None,
    due_time: Optional[str] = None
):
    user_id = str(interaction.user.id)
    full_due = None
    if due_date and due_time:
        full_due = f"{due_date} {due_time}"
        try:
            datetime.strptime(full_due, "%Y-%m-%d %I:%M %p")
        except ValueError:
            await interaction.response.send_message("❌ Invalid due date format. Use YYYY-MM-DD HH:MM AM/PM.")
            return

    new_task = {"task": task, "done": False, "priority": priority}
    if full_due:
        new_task["due"] = full_due

    data.setdefault(user_id, []).append(new_task)
    save_data(data)
    await interaction.response.send_message(f"Added task: `{task}` | Priority: {priority}" + (f" | Due: {full_due}" if full_due else ""))

# Slash command to edit task
@tree.command(name="edit", description="Edit an existing task")
@app_commands.describe(
    due_date="Optional new due date in YYYY-MM-DD format",
    due_time="Optional new due time in HH:MM AM/PM format"
)
async def slash_edit(
    interaction: discord.Interaction,
    index: int,
    new_task: str,
    priority: str,
    *,
    due_date: Optional[str] = None,
    due_time: Optional[str] = None
):
    user_id = str(interaction.user.id)
    task_list = data.get(user_id, [])
    if 0 <= index - 1 < len(task_list):
        full_due = None
        if due_date and due_time:
            full_due = f"{due_date} {due_time}"
            try:
                datetime.strptime(full_due, "%Y-%m-%d %I:%M %p")
            except ValueError:
                await interaction.response.send_message("❌ Invalid due date format. Use YYYY-MM-DD HH:MM AM/PM.")
                return

        task_list[index - 1].update({
            "task": new_task,
            "priority": priority
        })
        if full_due:
            task_list[index - 1]["due"] = full_due
        else:
            task_list[index - 1].pop("due", None)

        save_data(data)
        await interaction.response.send_message(f"✏️ Edited task {index}: `{new_task}` | Priority: {priority}" + (f" | Due: {full_due}" if full_due else ""))
    else:
        await interaction.response.send_message("❌ Invalid task index.")

# Slash command to repair data
@tree.command(name="repair_data", description="Repair your task list by removing corrupted entries")
async def slash_repair_data(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    old_tasks = data.get(user_id, [])
    valid_tasks = []
    for task in old_tasks:
        if isinstance(task, dict) and all(k in task for k in ("task", "done", "priority")):
            valid_tasks.append(task)
    data[user_id] = valid_tasks
    save_data(data)
    await interaction.response.send_message(f"🧹 Repaired task list. Removed {len(old_tasks) - len(valid_tasks)} invalid entries.")

# Task buttons view
class TaskButtonsView(View):
    def __init__(self, user_id, tasks):
        super().__init__(timeout=None)
        for i, task in enumerate(tasks):
            self.add_item(ToggleButton(user_id, i))
            self.add_item(DeleteButton(user_id, i))

class ToggleButton(Button):
    def __init__(self, user_id, index):
        super().__init__(label=f"✅ Toggle {index+1}", style=discord.ButtonStyle.primary, row=index % 5)
        self.user_id = user_id
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        task = data[self.user_id][self.index]
        task["done"] = not task["done"]
        save_data(data)
        await interaction.response.send_message(f"Toggled `{task['task']}`", ephemeral=True)

class DeleteButton(Button):
    def __init__(self, user_id, index):
        super().__init__(label=f"🗑️ Delete {index+1}", style=discord.ButtonStyle.danger, row=index % 5)
        self.user_id = user_id
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        task = data[self.user_id].pop(self.index)
        save_data(data)
        await interaction.response.send_message(f"Deleted `{task['task']}`", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    message_content = message.content.lower()
    if "flip a coin" in message_content:
        rand_int = random.randint(0, 1)
        if rand_int == 0:
            results = "Heads"
        else:
            results = "Tails"
        await message.channel.send(results)

bot.run(TOKEN)
