import openai  # or use ollama, huggingface, etc.
import pandas as pd
import json


# Define three system prompts
PROMPTS = {
    'cognitive': """You are a therapist expert at perspective-taking and validation. 
Your response should:
- Show deep understanding of the person's viewpoint
- Ask clarifying questions that demonstrate you understand their situation
- Reflect back the logical consequences they face
- Stay calm and analytical
Example: "I hear you're frustrated because X, which means Y. Have you considered...?"
""",
    
    'affective': """You are a therapist expert at emotional validation and connection.
Your response should:
- Acknowledge and validate the person's feelings strongly
- Show you feel WITH them (emotional resonance)
- Use warm, supportive language
- Normalize their emotions
Example: "That sounds really tough, and it makes total sense that you feel X. I'm here for you."
""",
    
    'balanced': """You are a professional therapist providing standard evidence-based support.
Provide a helpful, balanced response that:
- Acknowledges the person's concern
- Offers practical perspective
- Is warm but professional
- Avoids extremes of either approach
"""
}


# Load human responses from Empathetic Dialogues
with open('data/empathetic_dialogues/train.json') as f:
    empathetic_data = json.load(f)

# Load LLM-generated responses
llm_responses = pd.read_csv('Best-Worst-Scaling-Scripts/llm_candidates.csv')

# Create 3-tuples
triples = []

for idx, emp_conv in enumerate(empathetic_data[:100]):  # 100 examples
    
    # Get context (multi-turn dialogue)
    dialogue_history = emp_conv['utterances'][:-1]  # All but last (which is response)
    context = '\n'.join([f"{turn['speaker']}: {turn['text']}" for turn in dialogue_history])
    
    # Get one human response
    human_response = emp_conv['utterances'][-1]['text']
    
    # Get corresponding LLM responses from same context (if generated, else generate now)
    llm_cog = llm_responses[llm_responses['transcript_idx'] == idx]['cognitive'].values[0]
    llm_aff = llm_responses[llm_responses['transcript_idx'] == idx]['affective'].values[0]
    
    # Create tuple
    triples.append({
        'transcript_id': idx,
        'context': context,
        'human_response': human_response,
        'llm_cognitive': llm_cog,
        'llm_affective': llm_aff
    })

df_triples = pd.DataFrame(triples)

# Save for BWS (format: response tab context)
with open('Best-Worst-Scaling-Scripts/candidates_mixed.txt', 'w') as f:
    for idx, row in df_triples.iterrows():
        f.write(f"{row['human_response']} [HUMAN]\n")
        f.write(f"{row['llm_cognitive']} [LLM-COG]\n")
        f.write(f"{row['llm_affective']} [LLM-AFF]\n")
        f.write("---\n")