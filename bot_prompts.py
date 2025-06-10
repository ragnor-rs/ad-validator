# ============================================================================
# System Prompts
# ============================================================================

DEFAULT_SYSTEM_PROMPT = """You are a highly skilled legal compliance analyst specializing in advertising regulations. Your task is to analyze ad content and assess its compliance with relevant advertising laws and industry standards. This includes identifying potential violations, deceptive claims, required disclaimers, and age-restricted content. Your assessment should be clear and specific.

Note: Tailor your analysis based on the jurisdiction(s) provided or infer based on context if not specified."""

# ============================================================================
# Context Formatting Functions
# ============================================================================

def format_law_context(criteria: list) -> str:
    if len(criteria) == 0:
        return "None"

    law_context = ""
    for criterion in criteria:
        if len(law_context) > 0:
            law_context += "\n\n"
        law_context += f"From chapter \"{criterion['chapter_number']}. {criterion['chapter_title']}\", article \"{criterion['article_number']}. {criterion['article_title']}\", clause {criterion['clause_number']}:\n{criterion['description']}"

    return law_context

def format_ad_context(additional_data: list) -> str:
    if len(additional_data) == 0:
        return "None"
    
    ad_context = ""
    for item in additional_data:
        if len(ad_context) > 0:
             ad_context += "\n\n"
        ad_context += f"{item['question']}\n{item['answer']}" 

    return ad_context

def format_reqs(reqs: list) -> str:
    if len(reqs) == 0:
        return "None"
    
    ad_context = ""
    for item in reqs:
        if len(ad_context) > 0:
             ad_context += "\n"
        ad_context += f"- {item}"

    return ad_context

# ============================================================================
# Analysis Prompts
# ============================================================================

def get_ad_analysis_prompt(ad_text: str, detected_lang: str) -> str:
    return f"""I. Ad text to analyze:

{ad_text}


II. Jurisdiction:

{detected_lang} law


III. Instructions:
- Analyze this ad text from a legal perspective
- Highlight each possible violation on a separate line
- Do not group items
- Do not use any formatting"""

# ============================================================================
# Question Generation Prompts
# ============================================================================

def get_questions_prompt(ad_text: str, detected_lang: str, reqs: str) -> str:
    return f"""I. Ad text to analyze:

{ad_text}


II. Ad requirements:

{reqs}


III. Instructions:

- Generate questions in {detected_lang} to analyze if an ad meets the given requirements
- Give each question on a separate line
- Do not use any formatting
- Do not use bulleted neither numbered lists"""

# ============================================================================
# Response Generation Prompts
# ============================================================================

def get_response_prompt(ad_text: str, detected_lang: str, law_context: str, ad_context: str) -> str:
    return f"""I. Ad text to analyze:

{ad_text}


II. Jurisdiction:

{detected_lang} law


III. Relevant law:

{law_context}


IV. Ad context:

{ad_context}


V. Instructions:

- Analyze the given ad text from a legal perspective
- Apply the relevant law
- Apply the ad context
- Give the summary in {detected_lang}
- Be straight to the point, short and concise"""

# ============================================================================
# extract_requirements_prompt
# ============================================================================

def extract_requirements_prompt(law_context: str, detected_lang: str) -> str:
    return f"""I. The law:

{law_context}


II. Instructions:

- Extract requirements in {detected_lang} from the law
- Focus on requirements to any context surrounding the ad
- Do not give requirements about content
- Give each requirement on a separate line
- Do not use any formatting
- Do not use bulleted neither numbered lists""" 

# ============================================================================
# filter_applicable_requirements_prompt
# ============================================================================

def filter_applicable_requirements_prompt(ad_text: str, reqs: str) -> str:
    return f"""I. The ad:

{ad_text}


II. Requirements:

{reqs}


III. Instructions

- Extract requirements applicable to the given ad
- Give each requirement on a separate line
- Do not use any formatting
- Do not use bulleted neither numbered lists""" 

# ============================================================================
# filter_incomputable_requirements_prompt
# ============================================================================

def filter_incomputable_requirements_prompt(ad_text: str, reqs: str) -> str:
    return f"""I. The ad:

{ad_text}


II. Requirements:

{reqs}


III. Instructions

- Extract requirements you cannot evaluate based on the given ad
- Give each requirement on a separate line
- Do not use any formatting
- Do not use bulleted neither numbered lists""" 