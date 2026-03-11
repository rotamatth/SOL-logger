---
layout: default
title: LISP - A Rich Interaction Dataset and Loggable Interactive Search Platform
---

# Interactive Search Dataset & Resources

Explore the user study dataset, the loggable interactive search platform, and user profile data.  

**GitHub Repository:** [Project Website](https://github.com/irgroup/LISP_Dataset_and_Platform)

---

## 📂 Dataset and System

We used the [Conversational Argument Retrieval dataset](https://touche.webis.de/clef20/touche20-web/argument-retrieval-for-controversial-questions.html) from Touché 2020, based on the args.me corpus of Debate.org threads.  

> Dataset highlights:
> - 387,606 arguments across 50 TREC-style topics  
> - For this study: 26 relevant & controversial topics selected  
> - Removed arguments <150 or >3,000 characters  

Our search platform allows:


- **Query submission and reformulation**  
- **Display of top-10 arguments per page** (title + snippet, expandable to full text)  
- **Saving documents** as supporting or opposing a stance  
- **Reviewing saved documents**


> Note: Argument titles were automatically generated using Llama3.

---

## 🧑‍💻 Data Collection

### Participant Recruitment

- Students of Information Science at a German university  
- Voluntary, anonymous (pseudonyms), GDPR conform
- Study was conducted with informed consent
- Compensated with course credits

### Questionnaires (contained in the repository) 

- **Pre-study:** demographics, socioeconomic background, online activity, search experience, interest rating for 26 topics  
- **Post-study:** stance change, task difficulty rating

### Perceptual Speed Test

Participants completed a modified *Finding A’s Test*:

- Classify character strings for **ε** and **¥**  
- `j` = both present, `n` = not present  
- Time limit: 2 minutes, 30-second practice phase

---

## 🔄 Study Procedure

- Each participant worked on **two topics**: one high-interest, one no-interest  
- Task time limit: 10 minutes  
- Topic order pseudo-randomized  
- Interactions logged: queries, document views, saving, navigation  
- Optional comments collected (original + machine translation)

---

## 🛠 Resources

### Interaction Log Dataset

- 122 sessions, evenly split by topic interest  
- Logged: type, timestamp, session ID, document rank, score, length  
- Stop decisions and reasons recorded

### lisp – Loggable Interactive Search Platform

<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/welcome_screen.png" 
     alt="Search Interface" style="max-width:80%; margin:1em 0;">
</div>

<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/select_user_id.png" 
     alt="Search Interface" style="max-width:80%; margin:1em 0;">
</div>


<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/Example_Topic.png" 
     alt="Search Interface" style="max-width:80%; margin:1em 0;">
</div>


<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/result_page.png" 
     alt="Search Interface" style="max-width:80%; margin:1em 0;">
</div>


<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/result_page_marked.png" 
     alt="Search Interface" style="max-width:80%; margin:1em 0;">
</div>


<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/result_page_marked_plus_popup.png" 
     alt="Search Interface" style="max-width:80%; margin:1em 0;">
</div>


<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/stopping_reason.png" 
     alt="Search Interface" style="max-width:80%; margin:1em 0;">
</div>

<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/Endscreen.png" 
     alt="Search Interface" style="max-width:80%; margin:1em 0;">
</div>



- Enter queries, view results, navigate pages  
- Save documents with stance color coding  
- Summary popup at the end of each session  
- Customizable: labels, logging, dataset  





[Demo Perceptual Speed Test](https://andykruff.github.io/demo-ps-test/)

### User Profile Data

- Demographics, search experience, perceptual speed  
- Average perceptual speed: **101.66** (median: 103, SD: 28.51)

<div style="display:flex; gap:2em; flex-wrap:wrap; justify-content:center;">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/demographics_notitle.png" 
     alt="Demographics of Participants" style="max-width:45%;">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/ps_scores_new_bold.png" 
     alt="Perceptual Speed Scores" style="max-width:45%;">
</div>

---

## 🚀 Potential Applications


- **Interactive Information Retrieval:** study user behavior in argument retrieval and exploratory search  
- **Personalization & Recommendation:** influence of topic interest & perceptual speed on search strategies  
- **User Modeling:** predict search actions, stopping behavior, or stance selection  
- **Human-Computer Interaction:** evaluate interface designs for search platforms  
- **Educational Technologies:** assess learning and information acquisition strategies


<div style="text-align:center">
<img src="https://raw.githubusercontent.com/AndyKruff/Project-website/main/images/MM_withnumbers.png" 
     alt="Markov Model of User Interactions" style="max-width:65%; margin:1em 0;">
</div>

*Figure: Markov model of user interactions. Transitions from states marked with * to **REVIEW** and back were omitted for clarity. Transition probabilities indicated at the arrows and mean interaction times per state are averaged across all sessions. **MARK** and **PAGE** have no actual duration, assigned nominally 1 second.*
