# NRP Helper

## What it does

The National Research Platform (NRP) gives researchers access to computing resources, but using it can mean digging through a large amount of documentation just to answer a specific question. I built **NRP Helper** to make that documentation easier to use. Instead of searching through pages manually, a user can ask a normal question and get an answer based specifically on the NRP documentation, along with links to the pages the answer came from.

For example, someone could ask, **“How do I request a GPU for my Kubernetes pod?”** The bot searches the NRP documentation for the parts most related to that question, uses those passages to construct an answer, and shows the relevant sources. I also added a second capability for simple Kubernetes operations. If a user asks something like **“list pods”** or **“show logs for my-pod”**, the bot recognizes that as a command and gets the information directly from Kubernetes instead of trying to answer it from documentation. The deployed bot is therefore partly a documentation assistant and partly a small cluster troubleshooting tool.

## How it works

The first step happens before anyone asks a question. I take the NRP documentation files and split them into smaller pieces called **chunks**. I used chunks of about **2,000 characters with 400 characters of overlap**, so a sentence or explanation near a boundary does not completely lose its surrounding context. Each chunk also keeps the title and URL of the documentation page it came from. My dataset produced **547 chunks**.

Next, each chunk is converted into an **embedding** using the `qwen3-embedding` model. An embedding is basically a numerical representation of meaning: two pieces of text about similar ideas should end up relatively close together mathematically. I store those embeddings in a Chroma vector database.

When someone asks a question, I first clean or rewrite it into a better search query. Follow-up questions can also use recent conversation history so something like “How do I do that with a GPU?” can be turned into a standalone search. The question gets its own embedding, and Chroma finds the documentation chunks whose meanings are closest to it. The current version retrieves **10 candidates**, reranks them using additional signals such as words appearing in the title and text, and sends the **best five** to the language model.

The final prompt contains those five pieces of documentation plus instructions telling the model to answer from the provided material. Because each chunk still has its original page title and URL, the interface can attach sources to the answer. The language model is therefore not supposed to “know” the answer on its own. Its main job is to turn the retrieved documentation into a useful explanation.

## How it's deployed

I deployed the application on the NRP Kubernetes cluster. My Kubernetes manifest defines a **Deployment** to run the application, a **Service** to make the Streamlit application reachable inside the cluster, and an **Ingress** to give it a public HTTPS address. I also created a **ServiceAccount, Role, and RoleBinding** because the bot's Kubernetes tools need permission to inspect pods, logs, and deployments without giving the application unlimited access to the cluster.

The Python code, dependencies, documentation chunks, and prebuilt Chroma database were packaged into a Docker image. Kubernetes pulls that image and starts it as a pod. This also means the vector database does not have to be regenerated whenever the pod restarts: the indexed Chroma database is already part of the application image, so a replacement pod starts with the same database. For this mostly read-only use case, that was simpler than creating a database service.

The LLM token was different because I did **not** want it inside the code, Docker image, Git repository, or YAML as plain text. I stored it as a Kubernetes **Secret** named `nrp-llm-token`. The Deployment references that Secret, and Kubernetes injects its value into the pod as the `NRP_LLM_TOKEN` environment variable when the container starts. The application can read the token, but the actual token never appears in the manifest.

## What I tried — including what didn't work

The first version of retrieval was much simpler: embed the question, ask Chroma for the closest chunks, and give them to the model. That worked for straightforward questions, but I found that **“mathematically closest” did not always mean “best documentation page.”** A chunk might use similar language while another page had the actual instructions the user needed. I ended up adding query rewriting and reranking instead of relying only on vector similarity.

Follow-up questions created another problem. A user might first ask about creating a pod and then ask, “What if I need a GPU?” Searching literally for the second sentence throws away most of the context. I added a separate step that uses recent conversation history to rewrite the latest question into a standalone search query before retrieval.

Kubernetes caused a different class of problems. My first attempts to let the bot inspect the cluster failed because a pod does not automatically have permission to list other pods or read their logs. At one point, checking the bot's ServiceAccount permissions returned **“no.”** I had to understand the difference between the ServiceAccount, Role, and RoleBinding and then give the bot only the permissions each command actually required. The application now loads its in-cluster Kubernetes credentials automatically when deployed and falls back to my local Kubernetes configuration during development.

I also ran into deployment problems that had almost nothing to do with AI: pods stuck while containers were being created, image versions that were not actually the version I thought was running, old replicas terminating during rollouts, and scheduling problems on a particular cluster node. Those failures were useful because they changed how I thought about the project. Getting the chatbot code to work locally was only one part of building the system; getting the same code to run reliably inside Kubernetes was a separate engineering problem.

## Results

The final documentation index contained **547 chunks**. For each normal question, the bot searches **10 candidate chunks**, reranks them, and gives the **top five** to the language model. It can also bypass the RAG pipeline for supported Kubernetes requests and directly list pods and deployments, describe resources, or retrieve pod logs using the cluster API.

The failures I saw had a pattern. The language model usually was not the main problem. Bad answers were much more likely to start with **bad retrieval**: the wrong documentation page was retrieved, an important term disappeared from a follow-up question, or a semantically similar chunk outranked a more useful one. On the deployment side, the failures were usually permissions, configuration, image, or scheduling problems rather than Python logic. That was probably the biggest lesson from the project: a useful AI application depends on everything around the model working correctly.

## What I'd do next

* **Build a real evaluation set.** I would create 50–100 representative NRP questions with expected answers and expected source pages, then measure retrieval accuracy and answer quality instead of judging changes manually.
* **Improve retrieval further.** I would experiment systematically with chunk sizes, overlap, reranking weights, and possibly hybrid keyword + embedding search, recording which configuration actually performs best.
* **Expand Kubernetes tools carefully.** I would add useful troubleshooting actions such as inspecting events and resource usage, while continuing to restrict the ServiceAccount so the chatbot only receives the minimum permissions each feature requires.
<p align="right"><sub><sup>README created with help from ChatGPT</sup></sub></p>
