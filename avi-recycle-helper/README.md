# Recycling Documentation Assistant

## What it does

I built a recycling chatbot that answers questions using a collection of trusted recycling guides instead of relying on whatever the language model happens to know. The goal was to make recycling information easier to use: rather than searching through long documents, a user can ask a normal question and get a short answer based on the relevant sections of those documents. The assistant is also instructed to answer only from the documentation it is given, which reduces the chance that it confidently invents recycling rules.

For example, someone could ask, **“Can I recycle a greasy pizza box?”** The system does not simply send that question to an AI model. It first searches the recycling documentation for sections about pizza boxes, cardboard, food contamination, and related rules. It then gives the model only the most relevant pieces of documentation and asks it to answer from those. The interface also shows the source documents used for the answer, including their retrieval scores, so the user can check where the information came from.

## How it works

The pipeline starts with recycling documents that I converted into Markdown so they were easier for a program to process. I then split those documents into smaller, overlapping pieces called **chunks**. My chunks are about 2,000 characters long with 400 characters of overlap, which helps prevent useful information from being lost when an important paragraph happens to fall across a boundary. Each chunk keeps its title and a link back to its source.

Next, I convert every chunk into an **embedding** using `qwen3-embedding`. An embedding is basically a long list of numbers that represents the meaning of some text. I store those vectors in Chroma, a vector database. When a user asks a question, I turn the question into an embedding too and ask Chroma which chunks have the most similar meanings.

I found that plain vector similarity was not enough, so I added another ranking step. The program rewards chunks that contain important words from the question, cover a larger fraction of those words, or match useful two- and three-word phrases. It retrieves ten possibilities, reranks them, and sends the best five to the language model. The final prompt contains the question plus those selected chunks, and `qwen3-small` generates the answer. The program then displays links to the documents that supplied the context.

## How it is deployed

I deployed the application on Kubernetes. The main manifest contains three pieces: a **Deployment**, which runs the chatbot container; a **Service**, which gives the running application a stable internal network address; and an **Ingress**, which makes the site reachable through `avi-recycle-helper.nrp-nautilus.io`. The application itself runs on Streamlit on port 8501.

To get my code into the pod, I built a Docker image and pushed it as `aviatharvanand/recycle-helper`. The Kubernetes Deployment pulls that image and starts the Streamlit application. The Dockerfile installs the Python dependencies and copies the `rchatbot` application into the image. The Chroma database is a persistent on-disk database rather than something rebuilt for every question; the search code opens it from a fixed `recycling_chroma_db` directory. During deployment I packaged the already-built vector data with the application image, so replacing or restarting a pod could start again with the same indexed data rather than recomputing every embedding.

The language-model token was handled differently. I did **not** put the token in my Python code, Dockerfile, or Kubernetes YAML. I stored it as a Kubernetes Secret called `nrp-llm-token`. Kubernetes injects the value into the pod as the `NRP_LLM_TOKEN` environment variable when the container starts, and the Python program reads it from the environment.

## What I tried, including what didn't work

The most useful part of this project was that the first version was not especially good. My initial approach was basically: embed the question, take the closest chunks, and give them to the language model. That worked for obvious questions but failed when several documents used similar vocabulary. The nearest vector was not necessarily the chunk that actually contained the answer. I fixed this by adding keyword coverage, title matching, phrase matching, and reranking on top of vector similarity.

Questions themselves caused another problem. Something like “How do I recycle batteries?” contains several words that are useful to a human but not very useful for search. I added query rewriting that turns conversational questions into cleaner searches. Follow-up questions were harder: if someone first asked about batteries and then typed **“What about if they're damaged?”**, searching that sentence by itself lost the subject. I eventually added an AI rewrite step that uses recent conversation history to convert a follow-up into a standalone search query before retrieval.

Multi-part questions exposed another weakness. A single retrieved chunk might answer the first part perfectly but completely miss the second. I also ran into deployment problems along the way, including container/image rollout issues and getting the public Ingress/TLS configuration working. These were useful failures because they separated two very different problems: making the chatbot answer correctly and making the chatbot reliably run outside my laptop.

## Results

I tested the bot across several types of questions. It scored **62/65 on simple single-part questions (95%)**, **8/10 on simple multi-part questions (80%)**, **7/10 on complex questions (70%)**, and **10/10 on negative-scenario questions (100%)**. That is **87 correct out of 95 tests, or about 92% overall**.

The pattern matters more than the overall percentage. Simple factual questions were usually easy. The failures were concentrated in **multi-part and complex questions**, where the answer depended on retrieving several pieces of information or distinguishing between very similar recycling rules. That suggests the main remaining limitation is retrieval and context selection rather than simply needing a larger language model.

## What I'd do next

* **Improve multi-part retrieval:** split complicated questions into separate searches, retrieve evidence for each part, and combine the evidence before generating the answer.
* **Make evaluation automatic:** build a larger benchmark that runs after every retrieval or prompt change and reports accuracy by question type, instead of testing changes manually.
* **Improve source grounding:** connect individual claims in the answer directly to the specific document chunk that supports them, so citations show not just which sources were retrieved but exactly which source supports each statement.

<p align="right"><sub><sup>README was created with help of ChatGPT</sup></sub></p>
