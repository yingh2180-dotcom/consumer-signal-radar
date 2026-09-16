"""Original synthetic beauty test corpus; no source reviews or remote calls."""
import csv
import hashlib
import io
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent
RNG = random.Random(20260915)
TOPICS = {
    "包装": ("瓶盖扣得很稳，放在包里没有漏出来", "按压泵反复按了几次还是不出料"),
    "成分": ("成分说明写得清楚，方便核对自己的避雷项", "看了成分表仍不确定是否适合自己的情况"),
    "尺寸": ("这次的小规格很方便出差携带", "收到后觉得容量比想象中小"),
    "服务": ("客服耐心解释了使用顺序", "询问使用方法后一直没收到回复"),
    "功效": ("用了一段时间，干燥紧绷的感觉有所缓解", "连续用了几周，暂时没感觉到明显变化"),
    "价格": ("这次活动价格在我的预算内", "买完才看到更低的活动价格，有点犹豫"),
    "气味": ("气味很淡，涂完过一会儿就闻不到了", "香味对我来说偏浓，晚上用有点介意"),
    "使用体验": ("推开很顺，后续上妆也比较服帖", "涂完有些黏，叠加防晒时出现了搓泥"),
    "物流": ("配送很快，外箱收到时完整", "路上等了好几天，外箱还有些压痕"),
    "新鲜度": ("标注的日期清楚，剩余使用时间充足", "到手后发现剩余使用时间比预想短"),
    "真伪": ("包装上的核验步骤容易找到", "不知道怎样核验来源，准备先问客服"),
    "整体": ("总体使用感受符合我的预期", "整体体验没有达到预期，暂时不打算继续买"),
    "其他": ("希望以后能提供更详细的用量说明", "说明书的字有点小，阅读不太方便"),
}
CONTEXTS = ["我是干皮", "我是油皮", "我是混合皮", "我的肤质没有特别记录"]
ROUTINES = ["早上用的时候", "晚上护肤时", "出差这几天", "日常使用中", "刚开始尝试时"]
TAILS = ["仅记录我自己的使用感受。", "还会再观察一段时间。", "不同人的体验可能不一样。", "准备调整一下使用用量。"]


def csv_bytes(rows, fields):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def main():
    rows, expected = [], []
    topics = list(TOPICS)
    for index in range(1000):
        topic = topics[index % len(topics)]
        positive = index % 3 != 0
        phrase = TOPICS[topic][0 if positive else 1]
        case, action = "regular", "REVIEW_SEMANTICS"
        text = f"{RNG.choice(CONTEXTS)}，{RNG.choice(ROUTINES)}，{phrase}。{RNG.choice(TAILS)}"
        duplicate_of = ""
        if index < 20:
            text, case, action = ("" if index % 2 else "   "), "empty", "RULE_FILTER_EMPTY"
        elif index < 40:
            text, case, action = "此用户未填写具体评价", "template", "REVIEW_SEMANTICS"
        elif index < 60:
            other = topics[(index + 4) % len(topics)]
            text = f"{TOPICS[topic][0]}，不过{TOPICS[other][1]}。"
            case, action = "mixed", "KEEP_MULTIPLE_OPINIONS"
        elif index >= 980:
            source = rows[60 + index - 980]
            text, duplicate_of = source["review_text"], source["record_id"]
            case, action = "exact_text_duplicate", "REVIEW_DUPLICATE_NOT_AUTO_DELETE"
        rid = f"SYN-20260915-{index + 1:04d}"
        rows.append({
            "record_id": rid, "target_product_id": "", "source_origin": "synthetic_generated",
            "source_platform": "", "source_type": "purchase_review", "dataset_role": "pipeline_test",
            "brand": "演示品牌", "product_name": f"演示产品 {'ABC'[index % 3]}", "product_variant": "",
            "review_text": text, "publish_time_raw": "", "collection_time": "",
            "collection_method": "synthetic_demo", "sampling_strategy": "fixed_seed_scenario_composition",
            "sampling_stratum": "", "collection_batch_id": "SYN-20260915-v1", "query_keyword": "",
            "search_rank": "", "source_content_id": "", "parent_content_id": "", "original_record_id": "",
            "source_url": "", "data_kind": "synthetic_demo", "is_synthetic": "true",
            "generator_version": "v1", "generated_at": "2026-09-15",
        })
        expected.append({"record_id": rid, "test_case": case, "expected_action": action,
                         "duplicate_of": duplicate_of, "label_origin": "generator_fixture_not_human_gold"})
    assert len(rows) == len({r["record_id"] for r in rows}) == 1000
    assert all(r["dataset_role"] == "pipeline_test" and not r["target_product_id"] for r in rows)
    assert all(not r["source_platform"] and not r["source_url"] for r in rows)
    assert sum(not r["review_text"].strip() for r in rows) == 20
    for item in expected:
        if item["duplicate_of"]:
            original = next(r for r in rows if r["record_id"] == item["duplicate_of"])
            duplicate = next(r for r in rows if r["record_id"] == item["record_id"])
            assert original["review_text"] == duplicate["review_text"]
    files = {"synthetic_reviews.csv": csv_bytes(rows, list(rows[0])),
             "synthetic_expected.csv": csv_bytes(expected, list(expected[0]))}
    report = {"rows": len(rows), "unique_record_ids": 1000, "empty_text_rows": 20,
              "explicit_duplicate_cases": 20, "business_core_rows": 0, "real_product_assignments": 0,
              "is_human_gold": False, "is_model_evaluation": False, "checks_passed": True,
              "sha256": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    files["validation.json"] = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    for name, content in files.items():
        target = OUT / name
        if target.exists() and target.read_bytes() != content:
            raise RuntimeError(f"Refusing to overwrite changed artifact: {name}")
    for name, content in files.items():
        (OUT / name).write_bytes(content)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
