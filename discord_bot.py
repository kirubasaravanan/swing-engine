
import requests
import streamlit as st
import datetime

class DiscordBot:
    def __init__(self):
        # Load specialized webhooks
        self.url_bot = self._get_secret('discord_webhook_bot')
        self.url_stocks = self._get_secret('discord_webhook_stocks')
        
        # Fallback to generic if specialized missing (backward compat)
        self.url_generic = self._get_secret('discord_webhook')
        
        # Priority Assignment
        if not self.url_bot: self.url_bot = self.url_generic
        if not self.url_stocks: self.url_stocks = self.url_generic
        
    def _get_secret(self, key):
        """Fetch secure webhook from secrets"""
        try:
            if key in st.secrets:
                return st.secrets[key]
        except: pass
        return None

    def send_embed(self, title, description, color=0x00ff00, fields=None, webhook_url=None):
        """Send Fancy Embed to specific URL"""
        target_url = webhook_url
        if not target_url: return False
        
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        if fields:
            embed["fields"] = fields
            
        data = {"embeds": [embed]}
        
        try:
            response = requests.post(target_url, json=data)
            return response.status_code == 204
        except: return False

    # --- SPECIFIC ALERTS ---

    def notify_scan_complete(self, candidates):
        """Summary of Daily Scan -> BOT CHANNEL"""
        if not candidates: return
        
        top_5 = candidates[:5]
        field_list = []
        for c in top_5:
            field_list.append({
                "name": f"{c.get('Symbol')} (TQS: {c.get('TQS')})",
                "value": f"Price: {c.get('Price')} | Conf: {c.get('Confidence', 'N/A')}",
                "inline": False
            })
            
        self.send_embed(
            title="📊 Market Scan Complete",
            description=f"Found {len(candidates)} potential candidates.",
            color=0x3498db, # Blue
            fields=field_list,
            webhook_url=self.url_bot  # <--- Routing
        )

    def notify_new_entry(self, symbol, price, tqs):
        """New Entry -> STOCKS CHANNEL"""
        self.send_embed(
            title="📈 New Watchlist Candidate",
            description=f"**{symbol}** added to Watchlist.",
            color=0x2ecc71, # Green
            fields=[
                {"name": "Price", "value": str(price), "inline": True},
                {"name": "TQS Score", "value": f"{tqs}/10", "inline": True}
            ],
            webhook_url=self.url_stocks # <--- Routing
        )

    def notify_exit_signal(self, symbol, reason, price):
        """Exit Signal -> STOCKS CHANNEL"""
        self.send_embed(
            title="🚨 Exit Signal Detected",
            description=f"**{symbol}** flagged for exit.",
            color=0xe74c3c, # Red
            fields=[
                {"name": "Reason", "value": reason, "inline": True},
                {"name": "Current Price", "value": str(price), "inline": True}
            ],
            webhook_url=self.url_stocks # <--- Routing
        )

    def notify_job_status(self, message, is_error=False):
        """Generic Job Status -> BOT CHANNEL"""
        color = 0xe74c3c if is_error else 0x95a5a6 # Red or Grey
        self.send_embed(
            title="🤖 Bot Status Update",
            description=message,
            color=color,
            webhook_url=self.url_bot
        )
