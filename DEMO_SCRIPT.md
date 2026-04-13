# ClashX - Hackathon Demo Video Script

**Target Length:** ~5-6 minutes (within the 10-minute max)
**Format:** Screen recording with voiceover (camera-on optional for intro/outro)
**Tone:** Professional, fast-paced, focusing on value and live execution.
**Pacing:** ~130-150 spoken words per minute.

---

## 1. Problem & Idea (0:00 - 0:40)
**Visual:** Speaker on camera OR a split screen showing a trader staring anxiously at a volatile chart versus a peaceful autonomous robot.

**Audio / Voiceover:**
"Hi everyone, we're the team behind ClashX. 

When trading perpetuals on decentralized exchanges, human traders face a massive disadvantage. We have to sleep, we get emotional, we revenge-trade, and we miss perfect entries because we stepped away from our screens. While institutional players use sophisticated, emotionless algorithms to extract value 24/7, retail traders are stuck manually clicking buttons and managing exits across volatile markets.

The problem isn't that retail traders don't have good ideas—it's that they lack the infrastructure to systematically execute those ideas with strict risk management."

## 2. Solution Overview (0:40 - 1:20)
**Visual:** Cut to the ClashX Landing Page, scrolling smoothly to show the core value propositions (Visual Builder, AI Copilot, Copy Trading).

**Audio / Voiceover:**
"That’s why we built ClashX—a Pacifica-native autonomous trading bot platform.

ClashX transforms the user from a manual trader into a bot operator. Instead of placing discretionary trades, you design, test, and deploy automated strategies that execute continuously on Pacifica's on-chain perpetuals infrastructure. 

Whether you want to build a strategy using our drag-and-drop visual graph, generate one using our AI Copilot in plain English, or simply copy a top-performing creator from our public leaderboard, ClashX gives you hedge-fund-level execution tools without ever taking custody of your funds."

## 3. Live Product Walkthrough (1:20 - 4:20)
**Visual:** Screen recording moves to the web application. Fast-paced but clear cursor movements.

**Audio / Voiceover:**
*(1:20 - 1:50: Onboarding & Delegation)*
"Let's see it in action. First, we connect our wallet using Privy. Because ClashX is non-custodial, we use Pacifica's builder program. Here, we authorize a delegated agent wallet. This allows ClashX to execute trades on our behalf with strict builder fee limits, but we keep our private keys and our funds stay in our own wallet."

*(1:50 - 2:40: The Visual Builder & Copilot)*
"Now let's build a bot. I could use the drag-and-drop Visual Builder—connecting condition nodes like RSI or SMA to action nodes like 'Open Long' or 'Set Stop Loss'. 

But let's use the AI Copilot. I'll type: *'Create a mean reversion bot on SOL-PERP that goes long when the 15-minute RSI drops below 30, with a 2% stop loss.'* 
*(Visual: Type prompt, show Copilot generating the bot graph instantly)*. 
The Copilot understands Pacifica markets and instantly generates the valid strategy graph. It even ensures our risk management rules are attached."

*(2:40 - 3:20: Backtesting & Deployment)*
"Before risking capital, we hit 'Simulate'. 
*(Visual: Show the Backtesting Lab, fast-forwarding through a localized simulation or displaying the final PnL curve)*. 
The backtester runs this logic against historical candlestick data, accounting for Pacifica trading fees and slippage. Looks profitable. Let’s deploy it.
*(Visual: Click 'Deploy', status changes to 'Active')*. 
The Bot Runtime background worker immediately picks this up, evaluating our rules against live Pacifica WebSocket data every few seconds."

*(3:20 - 4:20: Leaderboard & Copy Trading)*
"But what if you don't want to build? We can go to the Marketplace and Leaderboard. 
*(Visual: Show the Leaderboard sorted by total PnL)*. 
Here are the top-performing public bots. Every bot has a Trust Score based on its health, risk grade, and uptime. 
I can click 'Mirror' on this top SOL breakout bot. 
*(Visual: Click Mirror, show scale factor slider)*. 
I set my scale factor to 50% of the creator's size. Now, whenever their bot triggers an execution event, our Copy Worker instantly replicates that Pacifica order to my wallet. We can even group multiple bots into a Portfolio Basket that automatically rebalances based on drift."

## 4. Pacifica Integration (4:20 - 5:10)
**Visual:** Split screen. Left side: Bot execution logs in the UI. Right side: Code snippets showing the Pacifica SDK (`place_order`, `get_positions`, WebSocket streams) and a block explorer showing real transactions.

**Audio / Voiceover:**
"ClashX is built exclusively for and deeply integrated with Pacifica. 

We aren't just a UI—our backend background workers maintain persistent WebSocket connections to Pacifica to evaluate market data in real-time. When a strategy triggers, we use the Pacifica Python SDK to craft and sign transactions using the user's delegated agent wallet. 

We handle market orders, limit orders, scaling in and out of positions, and reading live funding rates to ensure precise execution. By leveraging Pacifica's Builder authorization standard, we collect transparent builder fees seamlessly inside the protocol’s execution layer. Pacifica is the absolute core engine that makes this non-custodial, high-frequency automation possible."

## 5. Value & Impact (5:10 - 5:40)
**Visual:** Show the Telegram Bot integration flashing a notification ("Trade Executed: Long 50 SOL") on a mobile phone mockup, then pan to the Analytics Dashboard showing a rising equity curve.

**Audio / Voiceover:**
"The impact here is massive. We are leveling the playing field. 

Retail traders get strict risk management, 24/7 opportunity capture, and Telegram alerts, eliminating emotional trading errors. Strategy creators get a marketplace to monetize their edge through copy-trading scaling. And Pacifica gets a massive injection of systematic, predictable volume running continuously through its smart contracts."

## 6. What’s Next (5:40 - 6:00)
**Visual:** A clean roadmap slide or the speaker back on camera.

**Audio / Voiceover:**
"What's next for ClashX? Post-hackathon, we are expanding our portfolio allocator to support multi-asset cross-margin strategies, introducing TWAP and VWAP execution nodes, and allowing creators to gate their invite-only bots using NFTs. 

ClashX is ready to change how humans trade on Pacifica. Thank you."

---

### Tips for Recording:
1. **Prepare test data:** Ensure there are already bots running on your testnet account so the Dashboard and Analytics pages look active and populated.
2. **Pre-record load times:** If backtesting or AI generation takes 10+ seconds, speed up that specific part of the video in editing to maintain a punchy, fast pace.
3. **Cursor highlights:** Use a screen recording tool (like Screen Studio or Camtasia) that highlights mouse clicks and applies smooth zooming to keep the viewer focused on the specific UI element you are talking about.
4. **Follow the script loosely:** Speak naturally. Use the script as a structural guide rather than reading it like a robot.
