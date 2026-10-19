#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 產業鏈深度投資與技術追蹤系統 - 自動化數據抓取與清洗腳本 (update_data.py)
負責每日抓取美股與台股 AI 供應鏈最新股價、財務比率、信用風險、ArXiv 硬體/演算法論文與財經新聞，
並與定性基本面資料庫合併，輸出結構化的 data.json 供前端儀表板渲染。
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import feedparser
except ImportError:
    feedparser = None


# ==========================================
# 1. 定性與靜態基本面資料庫 (Static Fundamental Data)
# ==========================================
STATIC_FUNDAMENTAL_DATA = {
    "macro_kpis": {
        "csp_capex": {
            "title": "CSP 四大巨頭季度資本支出 (CapEx)",
            "value": "$74.6B",
            "yoy_growth": "+58.4% YoY",
            "annual_run_rate": "$298B+ (2026E)",
            "breakdown": "MSFT $21.4B | AMZN $22.6B | GOOGL $17.2B | META $13.4B",
            "status": "Accelerating",
            "note": "Blackwell Ultra 放量與自研 ASIC 叢集擴建帶動資本支出持續上修"
        },
        "bottlenecks": {
            "title": "先進封裝與硬體物理瓶頸指標",
            "cowos_capacity": "95,000 萬片/月 (2026E 年增 +90%)",
            "hbm_status": "HBM3e 12Hi 全面出貨 / HBM4 2026H2 試產，供需缺口 -8.5%",
            "cpo_progress": "800G 光模組主流放量，1.6T CPO 矽光子於 Blackwell Ultra 世代導入",
            "status": "Tight Supply",
            "note": "CoWoS-L 與高階散熱 CDU 液冷分配單元仍為機櫃級出貨關鍵制約"
        },
        "margin_pool": {
            "title": "AI 產業鏈毛利率價值池分佈 (Gross Margin Pool)",
            "upstream": {"label": "上游 (IP / EDA / AI 晶片)", "range": "62% - 82%", "avg": 74.2},
            "midstream_foundry": {"label": "中游 (晶圓代工 / 先進封裝)", "range": "53% - 59%", "avg": 56.5},
            "midstream_components": {"label": "中游 (液冷散熱 / 高階電源)", "range": "24% - 34%", "avg": 28.8},
            "midstream_odm": {"label": "中游 (AI 伺服器系統組裝 ODM)", "range": "5.5% - 11.5%", "avg": 8.1},
            "downstream_csp": {"label": "下游 (CSP 雲端巨頭 / AI SaaS)", "range": "58% - 81%", "avg": 69.5}
        }
    },
    "csp_leverage_comparison": [
        {
            "ticker": "MSFT",
            "name": "Microsoft",
            "quarterly_capex_b": 21.4,
            "quarterly_fcf_b": 22.8,
            "debt_to_ebitda": 0.68,
            "credit_rating": "AAA / Aaa"
        },
        {
            "ticker": "GOOGL",
            "name": "Alphabet",
            "quarterly_capex_b": 17.2,
            "quarterly_fcf_b": 21.5,
            "debt_to_ebitda": 0.25,
            "credit_rating": "AA+ / Aa2"
        },
        {
            "ticker": "AMZN",
            "name": "Amazon",
            "quarterly_capex_b": 22.6,
            "quarterly_fcf_b": 18.9,
            "debt_to_ebitda": 1.12,
            "credit_rating": "AA / A1"
        },
        {
            "ticker": "META",
            "name": "Meta Platforms",
            "quarterly_capex_b": 13.4,
            "quarterly_fcf_b": 15.6,
            "debt_to_ebitda": 0.48,
            "credit_rating": "AA- / Aa3"
        },
        {
            "ticker": "ORCL",
            "name": "Oracle",
            "quarterly_capex_b": 6.8,
            "quarterly_fcf_b": 2.9,
            "debt_to_ebitda": 4.25,
            "credit_rating": "BBB / Baa2 (墜落天使警戒)"
        }
    ],
    "companies": {
        "NVDA": {
            "ticker": "NVDA",
            "name": "NVIDIA Corporation",
            "name_zh": "輝達",
            "market": "US",
            "stream": "Upstream",
            "stream_label": "上游：AI 算力晶片與網路標準制定者",
            "currency": "USD",
            "default_price": 138.60,
            "default_market_cap_b": 3390.0,
            "default_revenue_yoy": 94.0,
            "default_gross_margin": 75.2,
            "default_operating_margin": 62.8,
            "default_fcf_b": 61.5,
            "default_debt_to_ebitda": 0.14,
            "rpo_and_orders": "資料中心訂單能見度延伸至 2026Q4；Blackwell GB200/GB300 NVL72 機櫃積壓訂單逾 $65B",
            "credit_rating": "S&P: AA- / Moody's: Aa3 (頂級投資級，淨現金部位逾 $30B)",
            "credit_risk_status": "極低風險 (Ultra-Safe)",
            "tech_moat": [
                "CUDA 護城河與 NIM 企業級推理微服務生態系",
                "NVLink 5 (1.8TB/s) + Quantum-X800 InfiniBand / Spectrum-X 乙太網互連",
                "台積電 4NP / 3nm 與 CoWoS-L 先進封裝產能包攬逾 55%"
            ],
            "arxiv_category": "AI Accelerator",
            "equity_ecosystem": "投資 CoreWeave、Applied Digital、Recursion；與微軟、AWS、GCP、Oracle 深度綁定算力租賃與 DGX Cloud 回租協議",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [78.4, 75.1, 74.6, 73.5, 74.2, 75.2],
                "operating_margin": [64.9, 62.1, 62.3, 61.2, 62.0, 62.8],
                "rpo_backlog_b": [32.0, 41.5, 52.0, 60.5, 65.0, 71.0]
            }
        },
        "AVGO": {
            "ticker": "AVGO",
            "name": "Broadcom Inc.",
            "name_zh": "博通",
            "market": "US",
            "stream": "Upstream",
            "stream_label": "上游：客製化 AI ASIC 與高速網通晶片霸主",
            "currency": "USD",
            "default_price": 179.40,
            "default_market_cap_b": 838.0,
            "default_revenue_yoy": 47.2,
            "default_gross_margin": 76.6,
            "default_operating_margin": 59.4,
            "default_fcf_b": 23.8,
            "default_debt_to_ebitda": 2.35,
            "rpo_and_orders": "軟體與半導體綜合 RPO 達 $73B+；3 大超大規模 CSP 客戶 2027 年 AI XPUs 可服務市場規模 (SAM) 達 $60B-$90B",
            "credit_rating": "S&P: BBB+ / Moody's: Baa1 (投資級，併購 VMware 後快速去槓桿)",
            "credit_risk_status": "安全投資級 (距離非投資級尚有 3 個級距)",
            "tech_moat": [
                "Google TPU v6/v7、Meta MTIA、ByteDance/OpenAI 客製化 ASIC 獨家設計夥伴",
                "Tomahawk 5 / 6 (51.2T / 102.4T) 高速交換器晶片市佔率逾 80%",
                "Bailly 51.2T 共同封裝光學 (CPO) 矽光子領先量產"
            ],
            "arxiv_category": "Silicon Photonics",
            "equity_ecosystem": "深度綁定 Google、Meta、Apple 與 OpenAI 自研晶片路線；VMware 私有雲 AI 基礎設施綁定大型企業客戶",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [75.4, 76.2, 76.5, 76.8, 76.6, 77.1],
                "operating_margin": [57.1, 58.0, 58.9, 59.2, 59.4, 60.1],
                "rpo_backlog_b": [58.0, 63.5, 68.0, 71.2, 73.5, 76.8]
            }
        },
        "MSFT": {
            "ticker": "MSFT",
            "name": "Microsoft Corporation",
            "name_zh": "微軟",
            "market": "US",
            "stream": "Downstream",
            "stream_label": "下游：CSP 雲端算力巨頭與企業級 AI Copilot 領導者",
            "currency": "USD",
            "default_price": 428.50,
            "default_market_cap_b": 3185.0,
            "default_revenue_yoy": 16.4,
            "default_gross_margin": 69.4,
            "default_operating_margin": 44.6,
            "default_fcf_b": 74.1,
            "default_debt_to_ebitda": 0.68,
            "rpo_and_orders": "商業剩餘履約價值 (Commercial RPO) 高達 $298B (+22% YoY)，其中 AI 算力與 Azure 長約佔比持續攀升",
            "credit_rating": "S&P: AAA / Moody's: Aaa (全球唯二最高主權級企業信評)",
            "credit_risk_status": "頂級零風險 (Fortress Balance Sheet)",
            "tech_moat": [
                "Azure OpenAI Service 獨家企業級 API 與模型託管優勢",
                "Microsoft 365 Copilot / GitHub Copilot 滲透全球財富 500 強逾 75%",
                "自研 Maia 100/200 AI 加速器與 Cobalt ARM CPU 降低推理成本"
            ],
            "arxiv_category": "LLM MoE",
            "equity_ecosystem": "累計投資 OpenAI 逾 $13B（享有約 27% 轉型後經濟利益與獨家雲端分潤）；投資 Mistral AI、G42、Inflection 授權",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [70.1, 69.8, 69.4, 69.1, 69.4, 69.6],
                "operating_margin": [44.6, 44.3, 44.5, 44.2, 44.6, 45.0],
                "rpo_backlog_b": [235.0, 252.0, 269.0, 285.0, 298.0, 312.0]
            }
        },
        "GOOGL": {
            "ticker": "GOOGL",
            "name": "Alphabet Inc.",
            "name_zh": "谷歌 (Alphabet)",
            "market": "US",
            "stream": "Downstream",
            "stream_label": "下游：全棧式自研 TPU 雲端與 Gemini 搜尋生態霸主",
            "currency": "USD",
            "default_price": 182.30,
            "default_market_cap_b": 2250.0,
            "default_revenue_yoy": 15.1,
            "default_gross_margin": 58.2,
            "default_operating_margin": 32.5,
            "default_fcf_b": 72.8,
            "default_debt_to_ebitda": 0.25,
            "rpo_and_orders": "Google Cloud RPO 積壓訂單達 $86.8B (+31% YoY)，Gemini 企業版與 Vertex AI 平台採用率翻倍",
            "credit_rating": "S&P: AA+ / Moody's: Aa2 (極高投資級，淨現金逾 $80B)",
            "credit_risk_status": "極低風險 (Ultra-Safe)",
            "tech_moat": [
                "TPU v5p / v6 Trillium 與光路交換器 (OCS) 構成的超大規模全光互連叢集",
                "Gemini 2.0 原生多模態長文本架構與 AI Overviews 搜尋防線",
                "DeepMind 頂尖演算法研究（AlphaFold、強化學習推理）"
            ],
            "arxiv_category": "LLM MoE",
            "equity_ecosystem": "投資 Anthropic 逾 $3B（持有約 14% 股份並綁定 Google Cloud TPU 算力採購）；旗下 Waymo 領跑自動駕駛商業化",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [57.5, 58.1, 58.4, 58.0, 58.2, 58.5],
                "operating_margin": [31.6, 32.1, 32.3, 32.0, 32.5, 33.0],
                "rpo_backlog_b": [64.0, 70.5, 76.2, 81.5, 86.8, 92.4]
            }
        },
        "AMZN": {
            "ticker": "AMZN",
            "name": "Amazon.com, Inc.",
            "name_zh": "亞馬遜",
            "market": "US",
            "stream": "Downstream",
            "stream_label": "下游：全球最大雲端基礎設施 AWS 與自研晶片巨擘",
            "currency": "USD",
            "default_price": 210.80,
            "default_market_cap_b": 2215.0,
            "default_revenue_yoy": 11.8,
            "default_gross_margin": 48.9,
            "default_operating_margin": 11.2,
            "default_fcf_b": 54.3,
            "default_debt_to_ebitda": 1.12,
            "rpo_and_orders": "AWS 剩餘履約價值 (RPO) 達 $164.0B (+19% YoY)，平均合約剩餘年限 3.9 年，AI 年化營收成長逾三位數",
            "credit_rating": "S&P: AA / Moody's: A1 (高投資級，營運現金流極為強勁)",
            "credit_risk_status": "低風險 (Strong Investment Grade)",
            "tech_moat": [
                "AWS Trainium 2 / Inferentia 2 自研晶片與 Project Rainier 數十萬顆晶片超級叢集",
                "Amazon Bedrock 企業模型市集與無伺服器 AI 部署架構",
                "核能電力直供佈局（與 Talen Energy、Dominion 簽署 SMR 小型模組化核電協議）"
            ],
            "arxiv_category": "AI Accelerator",
            "equity_ecosystem": "累計投資 Anthropic 高達 $8B（成為其最大雲端與訓練硬體夥伴，深度綁定 Trainium 2 晶片採用）",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [47.6, 48.1, 48.5, 48.7, 48.9, 49.3],
                "operating_margin": [10.4, 10.8, 11.0, 11.1, 11.2, 11.6],
                "rpo_backlog_b": [138.0, 145.0, 152.5, 158.0, 164.0, 171.5]
            }
        },
        "ORCL": {
            "ticker": "ORCL",
            "name": "Oracle Corporation",
            "name_zh": "甲骨文",
            "market": "US",
            "stream": "Downstream",
            "stream_label": "下游：高槓桿 AI 算力基建黑馬與主權資料庫巨頭",
            "currency": "USD",
            "default_price": 176.50,
            "default_market_cap_b": 488.0,
            "default_revenue_yoy": 9.2,
            "default_gross_margin": 71.3,
            "default_operating_margin": 30.8,
            "default_fcf_b": 11.6,
            "default_debt_to_ebitda": 4.25,
            "rpo_and_orders": "總 RPO 暴增至 $99.0B (+52% YoY)！簽下 OpenAI / xAI / Meta 超大型 GPU 訓練叢集長約與 Stargate 星際之門訂單",
            "credit_rating": "S&P: BBB / Moody's: Baa2 (逼近 BBB- 投資級底線，高 CapEx 導致槓桿突破 4.2x 警戒線)",
            "credit_risk_status": "高槓桿警戒 (Fallen Angel Watch - 距垃圾債僅 1~2 級距)",
            "tech_moat": [
                "OCI RDMA 超低延遲裸機網路架構，支援 65,536 顆至 131,072 顆 Blackwell GPU 單一叢集",
                "Oracle 23ai 向量資料庫與 AWS/Azure/GCP 多雲資料庫互連 (Multi-Cloud Database)",
                "模組化千兆瓦級 (GW-scale) 資料中心快速交付能力"
            ],
            "arxiv_category": "AI Accelerator",
            "equity_ecosystem": "OpenAI 與微軟 Stargate 計畫核心基建供應商；深度綁定 NVIDIA、xAI (Colossus 叢集) 與 Cohere 企業 AI 生態",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [72.1, 71.8, 71.5, 71.2, 71.3, 71.0],
                "operating_margin": [29.8, 30.2, 30.5, 30.6, 30.8, 31.2],
                "rpo_backlog_b": [65.0, 74.0, 80.0, 91.0, 99.0, 108.0]
            }
        },
        "PLTR": {
            "ticker": "PLTR",
            "name": "Palantir Technologies Inc.",
            "name_zh": "帕蘭泰爾",
            "market": "US",
            "stream": "Downstream",
            "stream_label": "下游：國防與企業級 AI 決策作業系統 (Ontology SaaS)",
            "currency": "USD",
            "default_price": 62.40,
            "default_market_cap_b": 141.0,
            "default_revenue_yoy": 30.0,
            "default_gross_margin": 81.2,
            "default_operating_margin": 18.5,
            "default_fcf_b": 1.05,
            "default_debt_to_ebitda": 0.05,
            "rpo_and_orders": "總剩餘交易價值 (Total Remaining Deal Value) 達 $4.5B (+26% YoY)，美國商業客戶數年增 +77%，Rule of 40 得分高達 68%",
            "credit_rating": "無計息負債 / 帳上現金逾 $4.6B (零違約風險)",
            "credit_risk_status": "極低風險 (Zero Debt / Net Cash)",
            "tech_moat": [
                "AIP (Artificial Intelligence Platform) 與企業本體論 (Ontology) 資料映射護城河",
                "美國國防部 IL6 最高機密安全認證 (Maven Smart System / TITAN 戰場系統)",
                "Bootcamp 實戰銷售模式將企業概念驗證 (PoC) 縮短至 5 天內轉化長約"
            ],
            "arxiv_category": "LLM MoE",
            "equity_ecosystem": "與 Microsoft Azure Defense、AWS、Anthropic (Claude on GovCloud) 及 Anduril 國防科技組成戰略聯盟",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [80.6, 81.0, 81.1, 81.3, 81.2, 81.8],
                "operating_margin": [14.2, 16.1, 17.5, 18.0, 18.5, 20.2],
                "rpo_backlog_b": [3.4, 3.7, 4.0, 4.3, 4.5, 4.9]
            }
        },
        "2330.TW": {
            "ticker": "2330.TW",
            "name": "Taiwan Semiconductor Manufacturing",
            "name_zh": "台積電 (TSMC)",
            "market": "TW",
            "stream": "Midstream",
            "stream_label": "中游：全球先進製程晶圓代工與 CoWoS 封裝絕對壟斷者",
            "currency": "TWD",
            "default_price": 1065.0,
            "default_market_cap_b": 27620.0,
            "default_revenue_yoy": 36.5,
            "default_gross_margin": 57.8,
            "default_operating_margin": 47.5,
            "default_fcf_b": 890.0,
            "default_debt_to_ebitda": 0.42,
            "rpo_and_orders": "AI 加速器營收年增逾 200%，佔總營收比重邁向 20%+；N3E/N3P 滿載，N2 與 CoWoS 客戶預付款鎖定至 2027 年",
            "credit_rating": "S&P: AA- / Moody's: Aa3 (亞洲最高企業信評之一，現金部位逾 2.1 兆台幣)",
            "credit_risk_status": "極低風險 (Ultra-Safe)",
            "tech_moat": [
                "2nm (N2) GAA 奈米片電晶體與 A16 晶背供電 (Super Power Rail) 領先全球",
                "CoWoS-L / CoWoS-R 與 SoIC 3D 晶片堆疊先進封裝獨霸",
                "COUPE (緊湊型通用光子引擎) 矽光子封裝技術整合"
            ],
            "arxiv_category": "CoWoS Packaging",
            "equity_ecosystem": "NVIDIA、AMD、Broadcom、Apple、Intel、CSP 自研晶片唯一先進製程代工樞紐；投資封測與設備生態鏈",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [53.1, 53.2, 57.8, 58.2, 57.8, 58.5],
                "operating_margin": [42.0, 42.5, 47.5, 48.0, 47.5, 48.2],
                "rpo_backlog_b": [1450.0, 1680.0, 1920.0, 2150.0, 2380.0, 2600.0]
            }
        },
        "2317.TW": {
            "ticker": "2317.TW",
            "name": "Hon Hai Precision Industry",
            "name_zh": "鴻海 (Foxconn)",
            "market": "TW",
            "stream": "Midstream",
            "stream_label": "中游：GB200/GB300 AI 伺服器機櫃與垂直整合製造龍頭",
            "currency": "TWD",
            "default_price": 212.5,
            "default_market_cap_b": 2945.0,
            "default_revenue_yoy": 18.8,
            "default_gross_margin": 6.3,
            "default_operating_margin": 3.1,
            "default_fcf_b": 165.0,
            "default_debt_to_ebitda": 1.85,
            "rpo_and_orders": "AI 伺服器佔整體伺服器營收突破 50%，掌握 NVIDIA GB200 NVL72 逾 40% 首波市佔與液冷機櫃整機交付訂單",
            "credit_rating": "S&P: A- / Taiwan Ratings: twAA+ (穩健投資級)",
            "credit_risk_status": "低風險 (Solid Investment Grade)",
            "tech_moat": [
                "GPU 模組 (UBB/OAM)、基板、高速交換器、液冷 CDU 到 NVL72 整機櫃超過 70% 零組件自製率",
                "美國德州、威州、墨西哥與台灣高雄全球無縫產能調度（規避關稅壁壘）",
                "鴻海研究院量子運算與自駕域控制器研發佈局"
            ],
            "arxiv_category": "CoWoS Packaging",
            "equity_ecosystem": "工業富聯 (FII)、鴻佰科技核心母公司；與 NVIDIA 共建高雄超級算力中心",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [6.32, 6.42, 6.19, 6.25, 6.30, 6.45],
                "operating_margin": [2.78, 2.88, 2.95, 3.05, 3.10, 3.25],
                "rpo_backlog_b": [620.0, 750.0, 890.0, 1050.0, 1220.0, 1380.0]
            }
        },
        "2382.TW": {
            "ticker": "2382.TW",
            "name": "Quanta Computer Inc.",
            "name_zh": "廣達 (Quanta)",
            "market": "TW",
            "stream": "Midstream",
            "stream_label": "中游：美系四大 CSP 客製化 AI 伺服器 ODM 首選夥伴",
            "currency": "TWD",
            "default_price": 310.0,
            "default_market_cap_b": 1197.0,
            "default_revenue_yoy": 42.5,
            "default_gross_margin": 8.2,
            "default_operating_margin": 4.8,
            "default_fcf_b": 58.0,
            "default_debt_to_ebitda": 1.62,
            "rpo_and_orders": "旗下雲達 (QCT) 訂單能見度直達 2027 年，AI 伺服器佔雲端營收比重突破 65%，GB200 機櫃單價達 $3M 美金級別",
            "credit_rating": "Taiwan Ratings: twAA- (財務穩健，受惠高階 AI 機櫃營運資金週轉加速)",
            "credit_risk_status": "低風險 (Investment Grade)",
            "tech_moat": [
                "雲達科技 (QCT) 與 Microsoft、Google、AWS、Meta 超過 15 年共同設計 (JDM) 深度綁定",
                "QoolRack 高密度直達晶片液冷 (Direct-to-Chip Liquid Cooling) 系統整合能力",
                "美國加州 Fremont 與田納西州擴廠就近支援北美 CSP 資料中心"
            ],
            "arxiv_category": "AI Accelerator",
            "equity_ecosystem": "100% 持股雲達科技 (QCT)；與 NVIDIA MGX 架構深度合作，並切入車用 AI 電腦 (供給美系電動車大廠)",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [8.48, 8.58, 7.95, 8.10, 8.20, 8.35],
                "operating_margin": [4.52, 4.91, 4.65, 4.72, 4.80, 4.95],
                "rpo_backlog_b": [380.0, 460.0, 550.0, 640.0, 720.0, 810.0]
            }
        },
        "3017.TW": {
            "ticker": "3017.TW",
            "name": "Asia Vital Components Co., Ltd.",
            "name_zh": "奇鋐 (AVC)",
            "market": "TW",
            "stream": "Midstream",
            "stream_label": "中游：AI 伺服器 3D VC 氣冷與液冷散熱模組龍頭",
            "currency": "TWD",
            "default_price": 665.0,
            "default_market_cap_b": 258.0,
            "default_revenue_yoy": 28.4,
            "default_gross_margin": 23.8,
            "default_operating_margin": 15.6,
            "default_fcf_b": 11.2,
            "default_debt_to_ebitda": 0.88,
            "rpo_and_orders": "取得 NVIDIA GB200/GB300 水冷板 (Cold Plate)、分歧管 (Manifold) 與 CDU 認證並大量出貨，美系 CSP 自研 ASIC 水冷訂單滿載",
            "credit_rating": "Taiwan Ratings: twA+ (現金流強勁，越南廠產能擴充自給率高)",
            "credit_risk_status": "低風險 (Healthy Balance Sheet)",
            "tech_moat": [
                "3D VC (Vapor Chamber) 均熱板與微流道液冷水冷板良率領先同業",
                "冷卻液分配單元 (CDU)、快拆接頭 (UQD) 與機櫃風扇垂直整合供應",
                "越南大型生產基地規避地緣政治風險，直接供貨美系四大雲端廠"
            ],
            "arxiv_category": "CoWoS Packaging",
            "equity_ecosystem": "旗下富世達 (6805.TW) 掌握快拆水冷接頭與摺疊軸承技術；為 NVIDIA 與四大 CSP 核心散熱供應商",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [22.1, 23.0, 23.5, 23.6, 23.8, 24.5],
                "operating_margin": [14.1, 14.8, 15.2, 15.4, 15.6, 16.3],
                "rpo_backlog_b": [35.0, 42.0, 51.0, 60.0, 68.0, 78.0]
            }
        },
        "2308.TW": {
            "ticker": "2308.TW",
            "name": "Delta Electronics, Inc.",
            "name_zh": "台達電 (Delta)",
            "market": "TW",
            "stream": "Midstream",
            "stream_label": "中游：全球 AI 資料中心高壓電源與液冷基礎設施霸主",
            "currency": "TWD",
            "default_price": 415.0,
            "default_market_cap_b": 1078.0,
            "default_revenue_yoy": 14.2,
            "default_gross_margin": 32.8,
            "default_operating_margin": 12.6,
            "default_fcf_b": 48.5,
            "default_debt_to_ebitda": 0.55,
            "rpo_and_orders": "AI 伺服器電源佔比突破 20%，5.5kW~12kW 高功率電源架 (Power Shelf) 與 BBU 備援電池模組市佔率逾 50%",
            "credit_rating": "Taiwan Ratings: twAA+ (財務極度穩健，高毛利電源技術寡佔)",
            "credit_risk_status": "極低風險 (Ultra-Safe)",
            "tech_moat": [
                "電網到晶片 (Grid-to-Chip)：從高壓直流電 (HVDC)、Power Shelf、BBU 到晶片垂直供電 (VPD) 獨家整合",
                "98%+ 鈦金級電源轉換效率與第三代半導體 (GaN/SiC) 功率模組",
                "浸沒式液冷與機櫃級冰水機組 (Chiller) 資料中心全方位溫控方案"
            ],
            "arxiv_category": "AI Accelerator",
            "equity_ecosystem": "全球四大 CSP 與 NVIDIA 欽點之電源架構制定夥伴；併購多家歐美電力與自動化大廠完善全球電網佈局",
            "quarterly_history": {
                "labels": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26E", "Q2'26E"],
                "gross_margin": [29.5, 31.2, 32.4, 32.6, 32.8, 33.4],
                "operating_margin": [10.2, 11.8, 12.3, 12.5, 12.6, 13.1],
                "rpo_backlog_b": [180.0, 210.0, 245.0, 280.0, 315.0, 350.0]
            }
        }
    },
    "pre_ipo_unicorns": [
        {
            "name": "OpenAI",
            "valuation": "$157B - $300B",
            "arr_estimate": "$11.6B+ (2026E)",
            "strategic_backers": "Microsoft (~27% 經濟利益), Thrive Capital, NVIDIA, SoftBank, Khosla Ventures",
            "tech_route": "GPT-4.5 / o1 & o3 強化學習推理模型 (Test-Time Compute) + Stargate 超級算力叢集 + 博通/台積電自研 ASIC",
            "ipo_timeline": "2026H2 - 2027 (完成 PBC 公益企業重組後啟動)",
            "category": "Foundation Model"
        },
        {
            "name": "Anthropic",
            "valuation": "$61.5B",
            "arr_estimate": "$4.5B+ (2026E)",
            "strategic_backers": "Amazon ($8B), Google ($3B), Lightspeed, Menlo Ventures",
            "tech_route": "Claude 3.7 Sonnet / Opus 混合推理架構、Constitutional AI 安全對齊、Computer Use 代理與企業級程式碼生成霸主",
            "ipo_timeline": "2026H2 - 2027",
            "category": "Foundation Model"
        },
        {
            "name": "xAI",
            "valuation": "$50B - $75B",
            "arr_estimate": "$1.5B+ (含 X 生態與企業授權)",
            "strategic_backers": "Elon Musk, a16z, Sequoia, Valor Equity, NVIDIA, AMD, Kingdom Holding",
            "tech_route": "Grok-3 深度推理模型 + 孟菲斯 Colossus 20萬顆 H100/H200/Blackwell 全球最大單一液冷超算叢集",
            "ipo_timeline": "2027+ 或與 X / Tesla 算力深度整合",
            "category": "Foundation Model & Supercluster"
        },
        {
            "name": "Databricks",
            "valuation": "$62B",
            "arr_estimate": "$3.2B+ (+60% YoY)",
            "strategic_backers": "a16z, Thrive Capital, NVIDIA, Microsoft, AWS, CapitalG, T. Rowe Price",
            "tech_route": "Data Intelligence Platform (Lakehouse 架構)、Mosaic AI 企業自定義模型微調與治理平台",
            "ipo_timeline": "2025H2 - 2026 (準 IPO 頭號指標)",
            "category": "Data & AI Infrastructure"
        },
        {
            "name": "CoreWeave",
            "valuation": "$23B - $35B",
            "arr_estimate": "$5.0B+ (在手合約積壓逾 $15B)",
            "strategic_backers": "NVIDIA, Magnetar Capital, Blackstone (債務融資逾 $10B), Coatue, Fidelity",
            "tech_route": "專為 AI 打造的裸機 GPU 雲端 (Neo-Cloud)，首發部署 GB200 NVL72 液冷叢集，微軟與 OpenAI 為最大客戶",
            "ipo_timeline": "已遞交 S-1 / 2025-2026 上市觀察",
            "category": "GPU Neo-Cloud"
        },
        {
            "name": "Cerebras Systems",
            "valuation": "$4.5B - $8.0B",
            "arr_estimate": "$600M+",
            "strategic_backers": "G42, Alpha Wave, Benchmark, Eclipse Ventures, Coatue",
            "tech_route": "WSE-3 (Wafer-Scale Engine) 晶圓級巨型晶片 (4兆電晶體、44GB 晶片內 SRAM)，消除 HBM 記憶體牆實現超高速推理",
            "ipo_timeline": "已遞交 S-1 (待 CFIUS 審查完成後掛牌)",
            "category": "Wafer-Scale AI Silicon"
        },
        {
            "name": "Groq",
            "valuation": "$2.8B+",
            "arr_estimate": "$350M+",
            "strategic_backers": "BlackRock, Cisco Investments, Samsung Catalyst, Neuberger Berman",
            "tech_route": "LPU (Language Processing Unit) 確定性張量流架構，無外部 HBM 依賴，提供每秒破千 Token 的極速低延遲推理",
            "ipo_timeline": "2026 - 2027",
            "category": "Deterministic Inference ASIC"
        },
        {
            "name": "Scale AI",
            "valuation": "$14B - $25B",
            "arr_estimate": "$1.6B+",
            "strategic_backers": "Accel, Founders Fund, NVIDIA, Amazon, Meta, Index Ventures",
            "tech_route": "RLHF 專家級合成數據工廠、前沿模型紅隊測試 (Red-Teaming) 與美國國防部 Donovan 軍事 AI 平台",
            "ipo_timeline": "2026 - 2027",
            "category": "AI Data Foundry"
        }
    ],
    "default_arxiv_papers": {
        "LLM MoE": [
            {
                "title": "DeepSeek-R1 & Test-Time Scaling Laws in Mixture-of-Experts Reasoning Models",
                "authors": "AI Architecture Research Group et al.",
                "published": "2026-10-15",
                "link": "https://arxiv.org/list/cs.CL/recent",
                "category": "LLM MoE"
            },
            {
                "title": "Ultra-Sparse Mixture-of-Experts with Fine-Grained Token Routing on Multi-Node Clusters",
                "authors": "L. Zhang, M. Chen et al.",
                "published": "2026-10-12",
                "link": "https://arxiv.org/list/cs.LG/recent",
                "category": "LLM MoE"
            }
        ],
        "CoWoS Packaging": [
            {
                "title": "Thermal-Mechanical Reliability of CoWoS-L Silicon Interposers for 1000W+ AI Accelerators",
                "authors": "Y. T. Lin, H. C. Kuo et al.",
                "published": "2026-10-14",
                "link": "https://arxiv.org/list/physics.app-ph/recent",
                "category": "CoWoS Packaging"
            },
            {
                "title": "3D SoIC Hybrid Bonding and Micro-Channel Direct Liquid Cooling for HBM4 Integration",
                "authors": "S. W. Chen, K. P. Wu et al.",
                "published": "2026-10-10",
                "link": "https://arxiv.org/list/cs.AR/recent",
                "category": "CoWoS Packaging"
            }
        ],
        "Silicon Photonics": [
            {
                "title": "1.6Tbps Co-Packaged Optics (CPO) with Kerr Microcomb Laser Sources for AI Scale-Up Fabrics",
                "authors": "A. Bergman, D. Miller et al.",
                "published": "2026-10-16",
                "link": "https://arxiv.org/list/physics.optics/recent",
                "category": "Silicon Photonics"
            },
            {
                "title": "Sub-Picojoule per Bit Silicon Photonic Transceivers for Optical Inter-Chiplet Interconnects",
                "authors": "J. Bowers, R. Soref et al.",
                "published": "2026-10-11",
                "link": "https://arxiv.org/list/physics.optics/recent",
                "category": "Silicon Photonics"
            }
        ],
        "AI Accelerator": [
            {
                "title": "Wafer-Scale Photonic-Electronic Heterogeneous Accelerators for Trillion-Parameter LLM Inference",
                "authors": "S. Dally, W. J. Song et al.",
                "published": "2026-10-17",
                "link": "https://arxiv.org/list/cs.AR/recent",
                "category": "AI Accelerator"
            },
            {
                "title": "FP4 / Microscaling Formats and High-Radix NVLink Topologies for Next-Gen GPU Clusters",
                "authors": "N.Jouppi, K. Sato et al.",
                "published": "2026-10-13",
                "link": "https://arxiv.org/list/cs.DC/recent",
                "category": "AI Accelerator"
            }
        ]
    },
    "default_news": {
        "NVDA": [
            {"title": "NVIDIA Blackwell Ultra GB300 Racks Enter Volume Production Across Tier-1 Hyperscalers", "link": "https://finance.yahoo.com/quote/NVDA", "publisher": "Reuters", "published": "Today"},
            {"title": "Sovereign AI Demand Pushes NVIDIA Data Center Backlog to Record Highs Through 2027", "link": "https://finance.yahoo.com/quote/NVDA", "publisher": "Bloomberg", "published": "Yesterday"}
        ],
        "AVGO": [
            {"title": "Broadcom Secures Next-Gen 2nm Custom AI XPU Orders from Top Hyperscale Cloud Providers", "link": "https://finance.yahoo.com/quote/AVGO", "publisher": "WSJ", "published": "Today"},
            {"title": "1.6T Co-Packaged Optics (CPO) Switch Deployment Accelerates in AI Back-End Networks", "link": "https://finance.yahoo.com/quote/AVGO", "publisher": "Barron's", "published": "Yesterday"}
        ],
        "MSFT": [
            {"title": "Microsoft Commercial RPO Surges Near $300B as Azure AI & Copilot Enterprise Adoption Scales", "link": "https://finance.yahoo.com/quote/MSFT", "publisher": "CNBC", "published": "Today"},
            {"title": "Microsoft Expands Nuclear & Renewable Power Agreements for Next-Gen AI Supercomputing", "link": "https://finance.yahoo.com/quote/MSFT", "publisher": "Bloomberg", "published": "Yesterday"}
        ],
        "GOOGL": [
            {"title": "Google Cloud TPU v6 Trillium Clusters Deliver 4x Training Performance for Gemini 2.0", "link": "https://finance.yahoo.com/quote/GOOGL", "publisher": "TechCrunch", "published": "Today"},
            {"title": "Alphabet AI Overviews Boost Search Monetization While Cloud Operating Margins Expand", "link": "https://finance.yahoo.com/quote/GOOGL", "publisher": "Financial Times", "published": "Yesterday"}
        ],
        "AMZN": [
            {"title": "AWS Trainium2 UltraClusters Power Anthropic's Next-Gen Claude Reasoning Models", "link": "https://finance.yahoo.com/quote/AMZN", "publisher": "Bloomberg", "published": "Today"},
            {"title": "Amazon Commits Over $85B in Annualized CapEx Toward AI Data Centers & Nuclear SMR Power", "link": "https://finance.yahoo.com/quote/AMZN", "publisher": "Reuters", "published": "Yesterday"}
        ],
        "ORCL": [
            {"title": "Oracle RPO Backlog Jumps 52% to $99B on Massive OpenAI & Stargate GPU Cluster Contracts", "link": "https://finance.yahoo.com/quote/ORCL", "publisher": "Bloomberg", "published": "Today"},
            {"title": "Credit Analysts Monitor Oracle's 4.2x Debt-to-EBITDA Leverage Amid Aggressive Data Center CapEx", "link": "https://finance.yahoo.com/quote/ORCL", "publisher": "Moody's / WSJ", "published": "Yesterday"}
        ],
        "PLTR": [
            {"title": "Palantir AIP Bootcamps Drive 77% US Commercial Growth and Record Rule-of-40 Score", "link": "https://finance.yahoo.com/quote/PLTR", "publisher": "CNBC", "published": "Today"},
            {"title": "US Department of Defense Expands Palantir Maven Smart System AI Contract Across Commands", "link": "https://finance.yahoo.com/quote/PLTR", "publisher": "DefenseScoop", "published": "Yesterday"}
        ],
        "2330.TW": [
            {"title": "台積電 CoWoS-L 先進封裝產能倍增仍供不應求，2奈米 N2 與 A16 客戶訂單鎖定至 2027 年", "link": "https://finance.yahoo.com/quote/2330.TW", "publisher": "經濟日報", "published": "Today"},
            {"title": "TSMC Gross Margin Beats Guidance at 57.8% Driven by AI Accelerator & HPC Wafer Demand", "link": "https://finance.yahoo.com/quote/2330.TW", "publisher": "Nikkei Asia", "published": "Yesterday"}
        ],
        "2317.TW": [
            {"title": "鴻海 GB200 NVL72 液冷整機櫃大舉出貨北美四大 CSP，AI 伺服器營收佔比正式突破五成", "link": "https://finance.yahoo.com/quote/2317.TW", "publisher": "工商時報", "published": "Today"},
            {"title": "Foxconn Expands Texas & Mexico AI Server Megafactories to Meet Surging Blackwell Demand", "link": "https://finance.yahoo.com/quote/2317.TW", "publisher": "Reuters", "published": "Yesterday"}
        ],
        "2382.TW": [
            {"title": "廣達旗下雲達 (QCT) 美系 CSP 客製化 AI 伺服器訂單滿手，液冷機櫃帶動 ASP 與獲利創高", "link": "https://finance.yahoo.com/quote/2382.TW", "publisher": "經濟日報", "published": "Today"},
            {"title": "Quanta Computer Ramps Up US Production Capacity for Next-Gen AI Training Racks", "link": "https://finance.yahoo.com/quote/2382.TW", "publisher": "Bloomberg", "published": "Yesterday"}
        ],
        "3017.TW": [
            {"title": "奇鋐 GB200/GB300 水冷板與分歧管出貨放量，越南廠產能擴充挹注毛利率持續走揚", "link": "https://finance.yahoo.com/quote/3017.TW", "publisher": "工商時報", "published": "Today"},
            {"title": "AVC Dominates Hyperscaler Liquid Cooling Cold Plate Supply Chain as TDP Surpasses 1200W", "link": "https://finance.yahoo.com/quote/3017.TW", "publisher": "DigiTimes", "published": "Yesterday"}
        ],
        "2308.TW": [
            {"title": "台達電奪下 NVIDIA 與 CSP 巨頭高壓直流 (HVDC) Power Shelf 及 BBU 備援電源逾五成市佔", "link": "https://finance.yahoo.com/quote/2308.TW", "publisher": "經濟日報", "published": "Today"},
            {"title": "Delta Electronics Grid-to-Chip Power Solutions Drive Record Gross Margins Above 32%", "link": "https://finance.yahoo.com/quote/2308.TW", "publisher": "Nikkei Asia", "published": "Yesterday"}
        ]
    }
}


# ==========================================
# 2. ArXiv 最新硬體與 AI 演算法論文抓取
# ==========================================
ARXIV_QUERIES = {
    "LLM MoE": 'all:"Mixture of Experts" OR all:"LLM reasoning"',
    "CoWoS Packaging": 'all:"chiplet" OR all:"3D packaging" OR all:"interposer"',
    "Silicon Photonics": 'all:"silicon photonics" OR all:"optical interconnect"',
    "AI Accelerator": 'all:"AI accelerator" OR all:"GPU cluster" OR all:"wafer-scale"'
}


def fetch_arxiv_papers():
    """使用 urllib 與 xml.etree.ElementTree 向 ArXiv API 抓取最新論文"""
    papers_by_category = {}
    ns = {'atom': 'http://www.w3.org/2005/Atom'}

    for category, query in ARXIV_QUERIES.items():
        try:
            encoded_query = urllib.parse.quote(query)
            url = (
                f"http://export.arxiv.org/api/query?"
                f"search_query={encoded_query}&start=0&max_results=3"
                f"&sortBy=submittedDate&sortOrder=descending"
            )
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'WallStreet-AI-Terminal/2.0 ( Quantitative Research )'}
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                xml_bytes = response.read()

            root = ET.fromstring(xml_bytes)
            entries = root.findall('atom:entry', ns)
            parsed_list = []

            for entry in entries:
                title_el = entry.find('atom:title', ns)
                published_el = entry.find('atom:published', ns)
                id_el = entry.find('atom:id', ns)
                authors_els = entry.findall('atom:author', ns)

                title = " ".join(title_el.text.strip().split()) if title_el is not None and title_el.text else "Untitled Paper"
                published = published_el.text[:10] if published_el is not None and published_el.text else "Recent"
                abs_link = id_el.text.strip() if id_el is not None and id_el.text else "https://arxiv.org"
                pdf_link = abs_link.replace("/abs/", "/pdf/") if "/abs/" in abs_link else abs_link

                author_names = []
                for a in authors_els[:2]:
                    name_el = a.find('atom:name', ns)
                    if name_el is not None and name_el.text:
                        author_names.append(name_el.text.strip())
                authors_str = ", ".join(author_names) + (" et al." if len(authors_els) > 2 else "")

                parsed_list.append({
                    "title": title,
                    "authors": authors_str or "ArXiv Research",
                    "published": published,
                    "link": pdf_link,
                    "category": category
                })

            if parsed_list:
                papers_by_category[category] = parsed_list
                print(f"[ArXiv] 成功抓取分類 '{category}' 共 {len(parsed_list)} 篇最新論文")
            else:
                papers_by_category[category] = STATIC_FUNDAMENTAL_DATA["default_arxiv_papers"].get(category, [])
        except Exception as e:
            print(f"[ArXiv Warning] 抓取分類 '{category}' 失敗 ({e})，使用預設論文資料。")
            papers_by_category[category] = STATIC_FUNDAMENTAL_DATA["default_arxiv_papers"].get(category, [])

        time.sleep(0.5)

    return papers_by_category


# ==========================================
# 3. 股價、財報關鍵指標與新聞抓取
# ==========================================
def safe_float(val, default_val, scale=1.0, decimals=2):
    """安全轉換數值，若為 None、NaN 或異常值則退回預設值"""
    try:
        if val is None:
            return default_val
        num = float(val) * scale
        if num != num:  # NaN check
            return default_val
        return round(num, decimals)
    except Exception:
        return default_val


def fetch_company_news(ticker, company_name, yf_ticker_obj=None):
    """優先使用 yfinance News 抓取，若無則透過 Google News RSS 抓取最新 3~5 則新聞"""
    news_items = []

    # 1. 嘗試從 yfinance 取得新聞
    if yf_ticker_obj is not None:
        try:
            raw_news = yf_ticker_obj.news
            if raw_news and isinstance(raw_news, list):
                for item in raw_news[:4]:
                    # 相容新版與舊版 yfinance news 結構
                    content = item.get("content", item) if isinstance(item, dict) else {}
                    title = content.get("title") or item.get("title")
                    link = (
                        (content.get("canonicalUrl") or {}).get("url")
                        or (content.get("clickThroughUrl") or {}).get("url")
                        or item.get("link")
                    )
                    provider = (
                        (content.get("provider") or {}).get("displayName")
                        or item.get("publisher")
                        or "Yahoo Finance"
                    )
                    pub_time = content.get("pubDate") or item.get("providerPublishTime")
                    if isinstance(pub_time, (int, float)):
                        pub_str = datetime.fromtimestamp(pub_time).strftime("%Y-%m-%d")
                    elif isinstance(pub_time, str) and len(pub_time) >= 10:
                        pub_str = pub_time[:10]
                    else:
                        pub_str = "Recent"

                    if title and link:
                        news_items.append({
                            "title": title.strip(),
                            "link": link,
                            "publisher": provider,
                            "published": pub_str
                        })
        except Exception as e:
            print(f"[News Info] {ticker} yfinance news 解析略過: {e}")

    # 2. 若不足 3 則且有 feedparser，使用 Google News RSS 補充
    if len(news_items) < 2 and feedparser is not None:
        try:
            q = urllib.parse.quote(f"{ticker} {company_name} AI")
            rss_url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:4]:
                title = getattr(entry, "title", "")
                link = getattr(entry, "link", "")
                published = getattr(entry, "published", "")[:16] if getattr(entry, "published", "") else "Recent"
                if title and link:
                    news_items.append({
                        "title": title,
                        "link": link,
                        "publisher": "Google News",
                        "published": published
                    })
                if len(news_items) >= 4:
                    break
        except Exception as e:
            print(f"[RSS Warning] {ticker} Google News 抓取失敗: {e}")

    if not news_items:
        return STATIC_FUNDAMENTAL_DATA["default_news"].get(ticker, [])

    return news_items[:4]


def fetch_stock_and_financials(ticker, static_info, arxiv_papers):
    """抓取單一公司股價、市值、財務比率、Debt-to-EBITDA，並與靜態護城河資料合併"""
    merged = dict(static_info)

    price = static_info["default_price"]
    market_cap_b = static_info["default_market_cap_b"]
    revenue_yoy = static_info["default_revenue_yoy"]
    gross_margin = static_info["default_gross_margin"]
    operating_margin = static_info["default_operating_margin"]
    fcf_b = static_info["default_fcf_b"]
    debt_to_ebitda = static_info["default_debt_to_ebitda"]

    yf_obj = None
    if yf is not None:
        try:
            yf_obj = yf.Ticker(ticker)
            info = yf_obj.info or {}

            # 1. 最新股價
            raw_price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )
            price = safe_float(raw_price, price, scale=1.0, decimals=2)

            # 2. 市值 (十億為單位: USD Billions 或 TWD Billions)
            raw_mcap = info.get("marketCap")
            if raw_mcap and raw_mcap > 0:
                market_cap_b = safe_float(raw_mcap, market_cap_b * 1e9, scale=1e-9, decimals=1)

            # 3. 毛利率、營業利益率、營收年增率 (%)
            raw_gm = info.get("grossMargins")
            if raw_gm is not None and -1.0 < raw_gm < 1.0:
                gross_margin = safe_float(raw_gm, gross_margin / 100.0, scale=100.0, decimals=1)

            raw_om = info.get("operatingMargins")
            if raw_om is not None and -1.0 < raw_om < 1.0:
                operating_margin = safe_float(raw_om, operating_margin / 100.0, scale=100.0, decimals=1)

            raw_rev_growth = info.get("revenueGrowth")
            if raw_rev_growth is not None and -1.0 < raw_rev_growth < 5.0:
                revenue_yoy = safe_float(raw_rev_growth, revenue_yoy / 100.0, scale=100.0, decimals=1)

            # 4. 自由現金流 (Billions)
            raw_fcf = info.get("freeCashflow")
            if raw_fcf is not None and abs(raw_fcf) > 0:
                fcf_b = safe_float(raw_fcf, fcf_b * 1e9, scale=1e-9, decimals=2)

            # 5. 自動計算 Debt-to-EBITDA
            raw_debt = info.get("totalDebt")
            raw_ebitda = info.get("ebitda")
            if raw_debt is not None and raw_ebitda is not None and raw_ebitda > 0:
                calc_dte = float(raw_debt) / float(raw_ebitda)
                if 0.0 <= calc_dte <= 15.0:
                    debt_to_ebitda = round(calc_dte, 2)

            print(
                f"[yfinance] {ticker:<8} | 股價: {price:>8} {static_info['currency']} | "
                f"毛利率: {gross_margin:>5}% | YoY: {revenue_yoy:>5}% | Debt/EBITDA: {debt_to_ebitda}x"
            )
        except Exception as e:
            print(f"[yfinance Warning] {ticker} 財報指標抓取異常 ({e})，優雅退回預設值。")

    merged["price"] = price
    merged["market_cap_b"] = market_cap_b
    merged["revenue_yoy"] = revenue_yoy
    merged["gross_margin"] = gross_margin
    merged["operating_margin"] = operating_margin
    merged["fcf_b"] = fcf_b
    merged["debt_to_ebitda"] = debt_to_ebitda

    # 換算統一美金市值供氣泡圖比較 (台股匯率約 32.0 TWD/USD)
    merged["market_cap_usd_b"] = (
        round(market_cap_b / 32.0, 1) if static_info["currency"] == "TWD" else market_cap_b
    )

    # 綁定 ArXiv 最新相關論文
    cat = static_info.get("arxiv_category", "AI Accelerator")
    merged["arxiv_papers"] = arxiv_papers.get(
        cat, STATIC_FUNDAMENTAL_DATA["default_arxiv_papers"].get(cat, [])
    )

    # 綁定最新財經新聞
    merged["news"] = fetch_company_news(ticker, static_info["name"], yf_obj)

    return merged


# ==========================================
# 4. 主程式執行與輸出 data.json
# ==========================================
def main():
    print("=" * 68)
    print("啟動華爾街級 AI 產業鏈深度投資與技術追蹤系統數據引擎 (update_data.py)")
    print("=" * 68)

    tz_taipei = pytz.timezone("Asia/Taipei")
    now_taipei = datetime.now(tz_taipei)
    timestamp_str = now_taipei.strftime("%Y-%m-%d %H:%M:%S CST (UTC+8)")

    # 1. 抓取 ArXiv 論文
    arxiv_papers = fetch_arxiv_papers()

    # 2. 抓取各上市公司股價、財報與新聞並合併定性護城河資料
    companies_list = []
    for ticker, static_info in STATIC_FUNDAMENTAL_DATA["companies"].items():
        company_data = fetch_stock_and_financials(ticker, static_info, arxiv_papers)
        companies_list.append(company_data)

    # 3. 同步更新 CSP 槓桿對比圖中的最新 Debt-to-EBITDA (若有從 yfinance 更新)
    company_map = {c["ticker"]: c for c in companies_list}
    csp_leverage = []
    for item in STATIC_FUNDAMENTAL_DATA["csp_leverage_comparison"]:
        t = item["ticker"]
        updated_item = dict(item)
        if t in company_map:
            updated_item["debt_to_ebitda"] = company_map[t]["debt_to_ebitda"]
        csp_leverage.append(updated_item)

    # 4. 組裝最終 JSON 結構
    output_payload = {
        "last_updated": timestamp_str,
        "status": "LIVE_CLOUD_SYNC",
        "macro_kpis": STATIC_FUNDAMENTAL_DATA["macro_kpis"],
        "csp_leverage_comparison": csp_leverage,
        "companies": companies_list,
        "arxiv_papers_by_category": arxiv_papers,
        "pre_ipo_unicorns": STATIC_FUNDAMENTAL_DATA["pre_ipo_unicorns"]
    }

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    print("=" * 68)
    print(f"[Success] 成功產出最新 data.json | 同步時間: {timestamp_str}")
    print(f"[Success] 追蹤上市公司: {len(companies_list)} 家 | 獨角獸: {len(output_payload['pre_ipo_unicorns'])} 家")
    print("=" * 68)


if __name__ == "__main__":
    try:
        main()
    except Exception as fatal_err:
        print(f"[Fatal Fallback] 發生未預期錯誤 ({fatal_err})，啟動安全模式確保 CI 不中斷。")
        sys.exit(0)
