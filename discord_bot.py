
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
        
        # FILTER: Only TSQ >= 9 as per user request
        top_picks = [c for c in candidates if int(c.get('TQS', 0)) >= 9]
        
        # Sort by TSQ desc
        top_picks.sort(key=lambda x: int(x.get('TQS', 0)), reverse=True)
        top_picks = top_picks[:10] # Cap at top 10 to avoid spam
        
        if not top_picks:
             # Optional: Notify that scan finished but nothing huge found
             self.notify_job_status("✅ Scan Complete. No TSQ 9/10 found.", is_error=False)
             return

        field_list = []
        for c in top_picks:
            # Emoji for TSQ
            icon = "🔥" if int(c.get('TQS', 0)) == 10 else "⚡"
            
            field_list.append({
                "name": f"{icon} {c.get('Symbol')} (TQS: {c.get('TQS')})",
                "value": f"Price: {c.get('Price')} | Conf: {c.get('Confidence', 'N/A')}",
                "inline": False
            })
            
        self.send_embed(
            title="💎 Top High-Quality Picks (TSQ 9-10)",
            description=f"Scan complete. Found {len(top_picks)} elite candidates.",
            color=0x9b59b6, # Purple
            fields=field_list,
            webhook_url=self.url_stocks  # <--- Send to Stocks Channel
        )

    def notify_market_update(self, pf_count, wl_count, top_picks_count):
        """General Market Update -> BOT CHANNEL"""
        self.send_embed(
            title="📊 Market Snapshot",
            description="Swing Engine Update",
            color=0x34495e, # Dark Blue
            fields=[
                {"name": "💼 Portfolio", "value": f"{pf_count} Active Positions", "inline": True},
                {"name": "⭐ Watchlist", "value": f"{wl_count} Tracked Stocks", "inline": True},
                {"name": "🔥 Top Picks", "value": f"{top_picks_count} (TSQ 9-10)", "inline": True}
            ],
            webhook_url=self.url_bot
        )

    def notify_exit_signal(self, symbol, reason, price):
        """Urgent Exit Alert -> STOCKS CHANNEL"""
        self.send_embed(
            title=f"🚨 EXIT SIGNAL: {symbol}",
            description=f"Reason: **{reason}**\nExit Price: ₹{price}",
            color=0xe74c3c, # Red
            webhook_url=self.url_stocks
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
