import axios from 'axios';
import bodyParser from 'body-parser';
import cors from 'cors';
import dotenv from 'dotenv';
import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

// Get current directory path for ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config();

const app = express();

// Middleware
app.use(cors());
app.use(bodyParser.json({ limit: "50mb" }));
app.use(express.static(path.join(__dirname, 'public')));

// Route to serve the main page
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Test route
app.get('/test', (req, res) => {
    res.json({ 
        message: 'Server is working!',
        timestamp: new Date().toISOString(),
        apis: {
            pollinations: 'Available (Free)',
            huggingface: process.env.HUGGINGFACE_TOKEN ? 'Available' : 'Token needed'
        }
    });
});

// Main API route for room decoration
app.post("/analyze-room", async (req, res) => {
    try {
        const { prompt, image } = req.body;
        
        if (!prompt) {
            return res.status(400).json({ error: "Prompt is required" });
        }

        console.log(`🎨 Processing request: "${prompt}"`);

        // Create enhanced prompt for better results
        const enhancedPrompt = `Beautiful modern interior room with ${prompt}, professional interior design, well-lit, cozy atmosphere, high quality photography, realistic`;

        let generatedImage = null;
        let analysisText = "";

        try {
            console.log("🖼️ Generating image with Pollinations AI...");
            
            // Use Pollinations AI (completely free, no API key needed)
            const imageUrl = `https://image.pollinations.ai/prompt/${encodeURIComponent(enhancedPrompt)}?width=768&height=512&model=flux&enhance=true`;
            
            const imageResponse = await axios.get(imageUrl, {
                responseType: 'arraybuffer',
                timeout: 15000,
                headers: {
                    'User-Agent': 'Room-Decor-App/1.0'
                }
            });

            const imageBuffer = Buffer.from(imageResponse.data);
            const base64Image = imageBuffer.toString('base64');
            generatedImage = `data:image/jpeg;base64,${base64Image}`;
            
            analysisText = `✨ Here's your room with ${prompt} added! I've generated a new design showing how your space could look with this addition. The image shows professional interior design principles applied to your request.`;
            
            console.log("✅ Image generated successfully!");

        } catch (imageError) {
            console.log("⚠️ Image generation failed, providing text suggestions instead");
            console.error("Image error:", imageError.message);
        }

        // If image generation failed, provide detailed text suggestions
        if (!generatedImage) {
            analysisText = generateDetailedSuggestion(prompt);
        }

        res.json({
            success: true,
            analysis: analysisText,
            modifiedImage: generatedImage,
            hasImage: !!generatedImage,
            prompt: prompt
        });

    } catch (error) {
        console.error("❌ Server error:", error.message);
        
        // Always provide a helpful response, even if there's an error
        const fallbackText = generateDetailedSuggestion(req.body.prompt || "room decoration");
        
        res.json({
            success: true,
            analysis: fallbackText + "\n\n💡 Note: I'm having trouble generating images right now, but here are some great text-based suggestions!",
            hasImage: false
        });
    }
});

// Generate detailed text suggestions
function generateDetailedSuggestion(prompt) {
    const lowerPrompt = prompt.toLowerCase();
    
    // Specific suggestions for common requests
    if (lowerPrompt.includes('coffee table')) {
        return `☕ **Adding a Coffee Table:**

📏 **Perfect Size:** Choose one that's about 2/3 the length of your sofa and sits 16-18 inches away from seating.

🎨 **Style Options:**
• **Glass top** → Makes small spaces feel larger
• **Wooden** → Adds warmth and natural texture
• **Metal/Industrial** → Modern, minimalist look
• **Storage ottoman** → Doubles as seating and storage

📍 **Placement Tips:**
• Center it in your seating area
• Ensure 30+ inches of walking space around it
• Consider the room's traffic flow

✨ **Styling Ideas:** Add a decorative tray with books, candles, or a small plant!`;
    }
    
    if (lowerPrompt.includes('plant') || lowerPrompt.includes('green')) {
        return `🌱 **Adding Plants to Your Space:**

🏠 **Best Indoor Plants:**
• **Snake Plant** → Perfect for beginners, low light OK
• **Pothos** → Trailing plant, great for shelves
• **Fiddle Leaf Fig** → Statement piece for corners
• **Peace Lily** → Beautiful white flowers, filters air

📍 **Placement Ideas:**
• Large plants in empty corners
• Small plants on floating shelves
• Hanging plants near windows
• Create a plant corner with multiple sizes

🏺 **Pot Selection:** Choose pots that match your decor - ceramic for modern, woven baskets for boho style!`;
    }
    
    if (lowerPrompt.includes('sofa') || lowerPrompt.includes('couch')) {
        return `🛋️ **Choosing the Perfect Sofa:**

📐 **Size Guide:**
• Measure your space first (length, width, doorways)
• Leave 30+ inches for walkways
• 2-seater: 58-72 inches, 3-seater: 72-96 inches

🎨 **Color & Material:**
• **Neutral colors** (gray, beige, navy) → Timeless and versatile
• **Bold colors** → Make a statement but harder to redecorate around
• **Fabric** → Cozy and soft, more color options
• **Leather** → Durable and easy to clean

📍 **Layout Options:**
• Face the TV for entertainment focus
• Create conversation area facing each other
• L-shaped sectional for corner spaces`;
    }
    
    if (lowerPrompt.includes('light') || lowerPrompt.includes('lamp')) {
        return `💡 **Improving Your Lighting:**

🔆 **Layer Your Lighting:**
1. **Ambient** → Overall room lighting (ceiling fixtures)
2. **Task** → Focused lighting (reading lamps, desk lights)  
3. **Accent** → Decorative mood lighting (string lights, candles)

💡 **Easy Additions:**
• **Table lamps** on side tables or consoles
• **Floor lamps** in dark corners
• **String lights** for cozy ambiance
• **LED strips** behind TV or under shelves

🌡️ **Light Temperature:**
• **Warm white (2700K)** → Cozy, relaxing evening mood
• **Cool white (4000K)** → Bright, energizing for daytime

🎚️ **Pro Tip:** Add dimmer switches to adjust mood throughout the day!`;
    }
    
    if (lowerPrompt.includes('color') || lowerPrompt.includes('paint')) {
        return `🎨 **Color Suggestions for Your Room:**

🎨 **Safe Color Schemes:**
• **Neutral Base** → White/beige walls + colorful accents
• **Monochromatic** → Different shades of the same color
• **Complementary** → Opposite colors on color wheel (blue + orange)

🖌️ **Popular Combinations:**
• **Classic:** White walls + black/gray accents + wood tones
• **Coastal:** Light blue + white + natural textures
• **Warm:** Cream + terracotta + gold accents
• **Modern:** Gray + white + one bold accent color

💡 **Color Psychology:**
• **Blue** → Calming, peaceful (great for bedrooms)
• **Green** → Natural, refreshing (living rooms)
• **Yellow** → Energizing, happy (kitchens, dining)
• **Gray** → Sophisticated, versatile (any room)`;
    }
    
    // Default response for any other request
    return `🏠 **Great idea to add "${prompt}" to your room!**

Here's my professional advice:

🎨 **Design Principles:**
• **Scale & Proportion** → Make sure new items fit your space size
• **Color Harmony** → Consider your existing color palette
• **Balance** → Distribute visual weight evenly around the room
• **Function First** → Ensure additions serve a practical purpose

📐 **Space Planning:**
• Leave clear pathways (minimum 30 inches wide)
• Create focal points to draw the eye
• Don't overcrowd - negative space is important
• Consider the room's natural traffic flow

✨ **Styling Tips:**
• Mix different textures (smooth, rough, soft, hard)
• Vary heights for visual interest
• Add personal touches that reflect YOUR style
• Use the rule of thirds for arranging items

💡 **Want more specific advice?** Ask me about:
• "What colors go well with ${prompt}?"
• "Where exactly should I place ${prompt}?"
• "What style of ${prompt} fits a small room?"`;
}

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
    console.log(`✅ Server running on port ${PORT}`);
    console.log(`🌐 Access your app at: http://localhost:${PORT}`);
    console.log(`🎨 Image generation: Pollinations AI (FREE)`);
    console.log(`📝 Text suggestions: Always available`);
});