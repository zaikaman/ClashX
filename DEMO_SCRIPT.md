# ClashX - Hackathon Demo Video Script

**Target Length:** ~5-6 minutes (within the 10-minute max)
**Format:** 100% Screen recording with voiceover (No camera/face required)
**Tone:** Professional, fast-paced, focusing on value and live execution.
**Pacing:** ~130-150 spoken words per minute.

---

## 1. Problem & Idea (0:00 - 0:40)
**Visual:** 
- Start with a clean, cinematic title card: "ClashX: Autonomous Trading on Pacifica".
- Fade into a split screen or graphic: On the left, a chaotic screen of a trader manually watching a volatile chart; on the right, a calm, unified dashboard of a bot fleet running systematically.

**Audio / Voiceover:**
"When trading perpetuals on decentralized exchanges, human traders face a massive disadvantage. We have to sleep, we get emotional, we revenge-trade, and we miss perfect entries because we stepped away from our screens. While institutional players use sophisticated, emotionless algorithms to extract value 24/7, retail traders are stuck manually clicking buttons and managing exits across volatile markets.

The problem isn't that retail traders don't have good ideas—it's that they lack the infrastructure to systematically execute those ideas with strict risk management."

## 2. Solution Overview (0:40 - 1:20)
**Visual:** 
- Cut to the ClashX Landing Page. 
- Scroll smoothly to highlight the core value propositions (Visual Builder, AI Copilot, Copy Trading).
- Cut to the main User Dashboard showing an active fleet of bots generating PnL.

**Audio / Voiceover:**
"That’s why we built ClashX—a Pacifica-native autonomous trading bot platform.

ClashX transforms the user from a manual trader into a bot operator. Instead of placing discretionary trades, you design, test, and deploy automated strategies that execute continuously on Pacifica's on-chain perpetuals infrastructure. 

Whether you want to build a strategy using our drag-and-drop visual graph, generate one using our AI Copilot in plain English, or simply copy a top-performing creator from our public leaderboard, ClashX gives you hedge-fund-level execution tools without ever taking custody of your funds."

## 3. Live Product Walkthrough (1:20 - 4:20)
**Visual:** 
- Keep the screen recording focused on the web application. Use a smooth mouse cursor and zoom in on key UI elements as they are mentioned.

**Audio / Voiceover:**
*(1:20 - 1:50: Onboarding & Delegation)*
"Let's see it in action. First, we connect our wallet using Privy. Because ClashX is non-custodial, we use Pacifica's builder program. Here, we authorize a delegated agent wallet. This allows ClashX to execute trades on our behalf with strict builder fee limits, but we keep our private keys and our funds stay in our own wallet."

*(1:50 - 2:40: The Visual Builder & Copilot)*
"Now let's build a bot. I could use the drag-and-drop Visual Builder—connecting condition nodes like RSI or SMA to action nodes like 'Open Long' or 'Set Stop Loss'. 

But let's use the AI Copilot. I'll type: *'Create a mean reversion bot on SOL-PERP that goes long when the 15-minute RSI drops below 30, with a 2% stop loss.'* 
*(Visual: Type prompt, show Copilot generating the bot graph instantly. Zoom in on the matched Risk Management node)*. 
The Copilot understands Pacifica markets and instantly generates the valid strategy graph. It even ensures our risk management rules are automatically attached."

*(2:40 - 3:20: Backtesting & Deployment)*
"Before risking capital, we hit 'Simulate'. 
*(Visual: Show the Backtesting Lab, fast-forwarding through a localized simulation or displaying the final PnL curve and metrics)*. 
The backtester runs this logic against historical candlestick data, accounting for Pacifica trading fees and slippage. Looks profitable. Let’s deploy it.
*(Visual: Click 'Deploy', status badge smooth-transitions to 'Active')*. 
The Bot Runtime background worker immediately picks this up, evaluating our rules against live Pacifica WebSocket data every few seconds."

*(3:20 - 4:20: Leaderboard & Copy Trading)*
"But what if you don't want to build? We can go to the Marketplace and Leaderboard. 
*(Visual: Show the Leaderboard sorted by total PnL. Hover over Trust Score badges)*. 
Here are the top-performing public bots. Every bot has a Trust Score based on its health, risk grade, and uptime. 
I can click 'Mirror' on this top SOL breakout bot. 
*(Visual: Click Mirror, show scale factor slider adjusting to 50%)*. 
I set my scale factor to 50% of the creator's size. Now, whenever their bot triggers an execution event, our Copy Worker instantly replicates that Pacifica order to my wallet. We can even group multiple bots into a Portfolio Basket that automatically rebalances based on drift."

## 4. Pacifica Integration (4:20 - 5:10)
**Visual:** 
- Split screen. Left side: Bot execution logs streaming in the UI. 
- Right side: Quick pan over code snippets showing the Pacifica SDK (`place_order`, WebSocket streams) and a block explorer showing real transactions originating from an agent wallet.

**Audio / Voiceover:**
"ClashX is built exclusively for and deeply integrated with Pacifica. 

We aren't just a basic UI wrapper—our backend workers maintain persistent WebSocket connections to Pacifica to evaluate market data in real-time. When a strategy triggers, we use the Pacifica SDK to craft and sign transactions using the user's delegated agent wallet. 

We handle market orders, limit orders, scaling in and out of positions, and reading live funding rates to ensure precise execution. By leveraging Pacifica's Builder authorization standard, we collect transparent builder fees seamlessly inside the protocol’s execution layer. Pacifica is the engine that makes this high-frequency, non-custodial automation possible."

## 5. Value & Impact (5:10 - 5:40)
**Visual:** 
- Show a mock-up of a mobile phone receiving a Telegram notification: "Trade Executed: Long 50 SOL".
- Transition to the Analytics Dashboard showing a rising equity curve and risk metrics.

**Audio / Voiceover:**
"The impact here is massive. We are leveling the playing field. 

Retail traders get strict risk management, 24/7 opportunity capture, and Telegram alerts, eliminating emotional trading errors. Strategy creators get a marketplace to monetize their edge through copy-trading. And Pacifica gets a massive injection of systematic, predictable volume running continuously through its smart contracts."

## 6. What’s Next (5:40 - 6:00)
**Visual:** 
- A clean, well-designed roadmap slide displaying 3 future milestones: Cross-Margin Strategies, TWAP/VWAP Nodes, NFT-gated Bots.

**Audio / Voiceover:**
"What's next for ClashX? Post-hackathon, we are expanding our portfolio allocator to support multi-asset cross-margin strategies, introducing TWAP and VWAP execution nodes, and allowing creators to gate their invite-only bots using NFTs. 

ClashX is ready to change how humans trade on Pacifica. Thank you."

---

### Tips for Recording:
1. **Prepare test data:** Ensure there are already bots running on your testnet account so the Dashboard and Analytics pages look active and populated.
2. **Pre-record load times:** If backtesting or AI generation takes 10+ seconds, pause your recording, wait for it to load, and then resume, or speed it up in editing.
3. **Cursor highlights:** Use a screen recording tool (like Screen Studio, Camtasia, or OBS with a cursor highlight plugin) that applies smooth zooming to keep the viewer focused on the specific UI element you are talking about.
4. **Voiceover sync:** Record your voiceover first in one continuous, clean take. Then, record your screen while listening to the audio to perfectly sync your clicks with your words.
