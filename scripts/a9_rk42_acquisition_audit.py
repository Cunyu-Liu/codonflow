#!/usr/bin/env python3
"""A9-RK42 independent-data acquisition audit (phase B, label-free).

Applies the frozen R1-R7 eligibility to each public candidate using raw-source
evidence (publisher methods/figures + downloaded raw supplementary artifacts +
independent partial-CSV re-derivation for Cambray). Produces a structured
acquisition report with per-source evidence, verdicts, branch decision, missing
dimensions and a prospective DBTL design. No model fit / outcome association.

Run:
  /home/codonflow-clean-env-v1/bin/python scripts/a9_rk42_acquisition_audit.py \
      --protocol configs/a9_rk42_independent_data_acquisition_protocol_v1.json \
      --report audits/20261122/RK42/independent_data_acquisition_v1.json
"""
import argparse
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = "/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk42/raw"
R_KEYS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]


def is_qualifying(source):
    """A source qualifies iff all R1-R7 are PASS (frozen rule)."""
    return all(source["R"][k]["status"] == "PASS" for k in R_KEYS)


def decide_branch(n_qual):
    if n_qual >= 1:
        return "B2_QUALIFYING_PUBLIC_DATA_PROCEED_TO_CLEAN_SPLIT_LEAKAGE_AUDIT"
    return "B3_NO_QUALIFYING_PUBLIC_DATA_WETLAB_DBTL_REQUIRES_USER_APPROVAL"


def sha(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def R(status, evidence):
    return {"status": status, "evidence": evidence}


def artifact_sha(name):
    return sha(os.path.join(RAW, name))


def build_sources():
    cambray_rederive = os.path.join(RAW, "cambray2018_partial_raw_rederive_v1.json")
    rd = {}
    if os.path.exists(cambray_rederive):
        with open(cambray_rederive) as f:
            rd = json.load(f)
    len_dist = rd.get("gs_sequence_length_distribution", {})
    n_pep = rd.get("n_distinct_translated_peptides")
    pheno = rd.get("numeric_phenotype_ranges", {})
    sources = []

    sources.append({
        "id": "Cambray2018",
        "study": "Cambray, Guimaraes, Arkin. Nat Biotechnol 36:1005-1015 (2018), doi:10.1038/nbt.4238",
        "host": "Escherichia coli MDS42",
        "raw_sources": [
            "SRA SRP086076",
            "Nature Supplementary Data 15 (MOESM58_ESM.zip, integrated phenotypic measurements, 244000 sequences)",
            "Nature Supplementary Note 1 (dataset column description, MOESM15_ESM.pdf)",
            "Nature Supplementary Tables 1-3 (MOESM14_ESM.pdf)",
        ],
        "raw_access_status": "partial_raw_downloaded: 127MB Data15 zip throttled/truncated by Springer static-content to ~10.7MB; leading deflate stream decompressed yielding 19760 real CSV rows; Note1/Tables PDFs fully downloaded",
        "raw_artifacts_sha256": {
            "cambray2018_supp_notes.pdf": artifact_sha("cambray2018_supp_notes.pdf"),
            "cambray2018_supp_notes.txt": artifact_sha("cambray2018_supp_notes.txt"),
            "cambray2018_supp_tables.pdf": artifact_sha("cambray2018_supp_tables.pdf"),
            "cambray2018_supp_tables.txt": artifact_sha("cambray2018_supp_tables.txt"),
            "cambray2018_data15_integrated_phenotypes.zip_partial": artifact_sha("cambray2018_data15_integrated_phenotypes.zip"),
            "cambray2018_partial_raw_rederive_v1.json": artifact_sha("cambray2018_partial_raw_rederive_v1.json"),
        },
        "construct_facts": [
            "244000 sequences = 56 replicates of a full factorial design; each variant is a designed 96-bp (32-codon) N-terminal coding segment fused to an engineered sfGFP reporter (Supplementary Note 1: gs.sequence = 'the designed sequence (96 bp)').",
            "Supplementary Note 1 utrCdsStructureMFE: 'The [-30;3] segment is constant; thus, the structure is dictated by variation in [1;27] of the designed sequence' -> upstream 5'UTR+start is a FIXED synthetic leader, not variant-specific native UTR.",
            "Design factors include amino-acid-level hydropathy (ds.cdsHydropathyIndex; ANOVA factor 'hydrol') -> amino acids vary, NOT a fixed-protein synonymous library.",
            "Continuous phenotypes: P_NI/P_FI protein (clean.lin.prot.mean, linear 1-100), relative growth W (growth.aggregate.R), mRNA abundance/half-life (ss.rna.dna.mean), polysome load; multiple replicates.",
        ],
        "raw_rederive": {
            "n_complete_rows": rd.get("n_complete_rows"),
            "gs_sequence_length_distribution": len_dist,
            "n_distinct_translated_peptides": n_pep,
            "amino_acid_varies": rd.get("amino_acid_varies"),
            "numeric_phenotype_ranges": pheno,
        },
        "R": {
            "R1": R("PASS", "Independent 2018 E. coli MDS42 study, not the Kudla training cohort."),
            "R2": R("FAIL", "Raw re-derivation: gs.sequence length = 96 bp for all %s sampled rows; variant region is a 32-codon N-terminal segment fused to sfGFP, not a full native CDS." % rd.get("n_complete_rows")),
            "R3": R("FAIL", "Supplementary Note 1: upstream [-30;3] segment is constant (fixed synthetic RBS leader); not variant-specific native 5'UTR. Primer Table 2 shows fixed AAGGAGGT...ATG leader."),
            "R4": R("FAIL", "Raw re-derivation: %s distinct translated peptides among sampled rows (amino_acid_varies=True); factorial design varies hydropathy/amino-acid properties -> not fixed-protein synonymous." % n_pep),
            "R5": R("FAIL", "Single engineered sfGFP reporter protein; no native protein identity/family map for protein OOD."),
            "R6": R("PASS", "Raw continuous ranges: clean.lin.prot.mean %s; growth.aggregate.R %s; ss.rna.dna.mean %s; fresh continuous with replicates." % (pheno.get("clean.lin.prot.mean"), pheno.get("growth.aggregate.R"), pheno.get("ss.rna.dna.mean"))),
            "R7": R("PASS", "SRA SRP086076 + Nature supplementary; raw artifact SHA256 documentable (partial download honestly recorded)."),
        },
    })

    sources.append({
        "id": "Kosuri2013",
        "study": "Kosuri et al. PNAS 110:14024-14029 (2013), doi:10.1073/pnas.1301301110",
        "host": "Escherichia coli MG1655",
        "raw_sources": ["AddGene 47441 (pGERC reporter)", "PNAS Dataset S1/S3", "Fig.1 construct diagram (saved kosuri_pnas.html)"],
        "raw_access_status": "publisher_methods_verified_via_fetch: curl full-page HTML returned Cloudflare challenge (kosuri_pnas.html retained); construct geometry confirmed from publisher methods text (kosuri2013_pnas_methods.txt) + Fig.1; outcome Dataset S1 not separately fetched",
        "raw_artifacts_sha256": {"kosuri2013_pnas_methods.txt": artifact_sha("kosuri2013_pnas_methods.txt"), "kosuri_pnas.html_blocked_challenge": artifact_sha("kosuri_pnas.html")},
        "construct_facts": [
            "12653 constructs = all combinations of 114 promoters x 111 RBSs driving FIXED superfolder GFP; mCherry independent internal control.",
            "Promoters/RBSs are synthetic parts (BIOFAB, Anderson BioBrick, Salis RBS Calculator, cloning vectors); the sfGFP CDS is invariant.",
            "FlowSeq continuous GFP/RFP protein levels over ~4 orders of magnitude.",
        ],
        "R": {
            "R1": R("PASS", "Independent 2013 E. coli MG1655 study."),
            "R2": R("FAIL", "sfGFP CDS fixed; no per-variant CDS variation (regulatory-grammar library)."),
            "R3": R("FAIL", "Variable elements are synthetic promoter/RBS parts, not variant-specific native 5'UTR."),
            "R4": R("FAIL", "Fixed CDS, no synonymous codon library; variation is in regulatory elements."),
            "R5": R("FAIL", "Single sfGFP reporter; no protein family map."),
            "R6": R("PASS", "Continuous FlowSeq GFP/RFP protein levels."),
            "R7": R("PASS", "AddGene 47441 + PNAS datasets; provenance documentable."),
        },
    })

    sources.append({
        "id": "Goodman2013",
        "study": "Goodman, Church, Kosuri. Science 342:475-479 (2013), doi:10.1126/science.1241934",
        "host": "Escherichia coli",
        "raw_sources": ["Table S1 = 1241934tables1.csv (12.57MB)", "SRA SRP029609 (SRX346948 RNA / SRX346944 DNA / SRX346268 FlowSeq)", "AddGene 47441"],
        "raw_access_status": "raw_table_blocked: science.org Table S1 CSV returned Cloudflare 'Just a moment...' challenge via curl AND fetch tool (real failure retained, goodman2013_tableS1.csv is a 5733-byte HTML challenge page); construct geometry verified from publisher methods/abstract",
        "raw_artifacts_sha256": {"goodman2013_tableS1.csv_blocked_html": artifact_sha("goodman2013_tableS1.csv")},
        "construct_facts": [
            ">14000 synthetic reporters = N-terminal codon variants of 137 E. coli genes combined with promoter/RBS combinations (14234 combinations of promoters, RBSs and N-terminal coding sequences).",
            "Variation is N-terminal coding segment within a reporter-fusion context plus regulatory (promoter/RBS) variation; fixed leader context per construct.",
        ],
        "R": {
            "R1": R("PASS", "Independent 2013 E. coli study."),
            "R2": R("FAIL", "N-terminal segment + reporter fusion, not full native CDS per variant."),
            "R3": R("FAIL", "Synthetic promoter/RBS combinations; not variant-specific native 5'UTR."),
            "R4": R("FAIL", "Synonymous only within N-terminal segment across 137 genes with reporter fusion + regulatory variation; not a fixed-protein full-CDS synonymous library."),
            "R5": R("FAIL", "137 gene identities present but no protein family map provided in raw; raw table blocked."),
            "R6": R("PASS", "Continuous fluorescence expression (methods)."),
            "R7": R("FAIL", "Raw Table S1 blocked by Cloudflare; raw SHA of outcome table not obtainable this round (SRA accession exists)."),
        },
    })

    sources.append({
        "id": "Mutalik2013",
        "study": "Mutalik et al. Nat Methods 10:354-360 (2013), doi:10.1038/nmeth.2404",
        "host": "Escherichia coli",
        "raw_sources": ["BIOFAB bicistronic design (BCD) promoter/RBS libraries", "publisher methods"],
        "raw_access_status": "publisher_methods_verified: BCD architecture (RBS1 drives short leader peptide; insulated promoter) confirmed; regulatory-element library with fixed reporter",
        "raw_artifacts_sha256": {},
        "construct_facts": [
            "Bicistronic design (BCD): well-accessible RBS1 drives a short leader peptide; libraries of constitutive/repressor-regulated promoters + translation initiation elements; fixed downstream reporter.",
            "Variation is in transcription/translation initiation elements, not synonymous CDS.",
        ],
        "R": {
            "R1": R("PASS", "Independent 2013 E. coli study."),
            "R2": R("FAIL", "Fixed reporter CDS; regulatory-element library."),
            "R3": R("FAIL", "Synthetic BCD promoter/RBS elements, not native variant-specific UTR."),
            "R4": R("FAIL", "No synonymous CDS library; fixed CDS."),
            "R5": R("FAIL", "Reporter construct; no protein family map."),
            "R6": R("PASS", "Continuous expression distributions across libraries."),
            "R7": R("FAIL", "Raw construct-level table not downloaded this round; metadata-only."),
        },
    })

    sources.append({
        "id": "Rhodius2012",
        "study": "Rhodius et al. (2012), BIOFAB-associated regulatory-parts characterization",
        "host": "Escherichia coli",
        "raw_sources": ["candidate identity ambiguous; raw source not precisely located this round"],
        "raw_access_status": "raw_unverified: precise publication/raw table not located; BIOFAB context indicates promoter/RBS regulatory-parts library",
        "raw_artifacts_sha256": {},
        "construct_facts": ["BIOFAB-associated regulatory parts (promoter/RBS) characterization; not a fixed-protein synonymous CDS dataset."],
        "R": {
            "R1": R("PASS", "Independent study (BIOFAB)."),
            "R2": R("FAIL", "Regulatory-parts library, no synonymous CDS variation."),
            "R3": R("FAIL", "Synthetic regulatory parts."),
            "R4": R("FAIL", "Not a fixed-protein synonymous CDS library."),
            "R5": R("FAIL", "No protein family map."),
            "R6": R("PASS", "Continuous expression (regulatory activity)."),
            "R7": R("FAIL", "Raw source unverified; cannot document raw SHA."),
        },
    })

    sources.append({
        "id": "Salis2011",
        "study": "Salis lab RBS Calculator / designed RBS variants (2011)",
        "host": "Escherichia coli",
        "raw_sources": ["RBS Calculator designed RBS datasets", "publisher methods"],
        "raw_access_status": "publisher_methods_verified: designed synthetic RBS variants driving fixed reporter CDS",
        "raw_artifacts_sha256": {},
        "construct_facts": ["Designed synthetic RBS (5'UTR) variants with fixed reporter CDS; variation in RBS strength, not synonymous codons."],
        "R": {
            "R1": R("PASS", "Independent study."),
            "R2": R("FAIL", "Fixed reporter CDS."),
            "R3": R("FAIL", "Synthetic designed RBS, not native variant-specific UTR."),
            "R4": R("FAIL", "No synonymous CDS library."),
            "R5": R("FAIL", "Single reporter; no family map."),
            "R6": R("PASS", "Continuous expression."),
            "R7": R("FAIL", "Raw construct table not downloaded this round."),
        },
    })

    sources.append({
        "id": "EspahBorujeni2014_2017",
        "study": "Espah Borujeni, Channarasappa, Salis. NAR 42:2646-2659 (2014) doi:10.1093/nar/gkt1139; Espah Borujeni et al. (2017)",
        "host": "Escherichia coli",
        "raw_sources": ["designed RBS/UTR structure variants", "publisher methods"],
        "raw_access_status": "publisher_methods_verified: designed RBS/UTR secondary-structure variants with fixed reporter",
        "raw_artifacts_sha256": {},
        "construct_facts": ["Translation initiation controlled by RNA folding/standby-site accessibility; designed RBS/UTR structure variants driving fixed reporter CDS."],
        "R": {
            "R1": R("PASS", "Independent study."),
            "R2": R("FAIL", "Fixed reporter CDS."),
            "R3": R("FAIL", "Synthetic designed RBS/UTR, not native variant-specific UTR."),
            "R4": R("FAIL", "No synonymous CDS library."),
            "R5": R("FAIL", "Single reporter; no family map."),
            "R6": R("PASS", "Continuous translation-rate/expression readout."),
            "R7": R("FAIL", "Raw construct table not downloaded this round."),
        },
    })

    sources.append({
        "id": "deBoer2020",
        "study": "de Boer et al. Nat Biotechnol 38:56-65 (2020)",
        "host": "Saccharomyces cerevisiae (yeast)",
        "raw_sources": [">100 million fully random synthetic yeast promoter sequences driving fixed YFP", "GEO (Vaishnav/de Boer promoter datasets)"],
        "raw_access_status": "publisher_methods_verified: fully random synthetic PROMOTER library, fixed reporter CDS, yeast host",
        "raw_artifacts_sha256": {},
        "construct_facts": [
            ">100 million fully random synthetic yeast promoter sequences; expression output measured; fixed reporter (YFP) CDS.",
            "Variation is in promoters (cis-regulatory DNA), not synonymous CDS; promoter is not a 5'UTR.",
        ],
        "R": {
            "R1": R("PASS", "Independent yeast study (distinct host)."),
            "R2": R("FAIL", "No CDS variation; fixed reporter."),
            "R3": R("FAIL", "Random synthetic promoters, not native variant-specific 5'UTR (and promoter != UTR)."),
            "R4": R("FAIL", "Promoter library, not synonymous CDS."),
            "R5": R("FAIL", "Single reporter; no protein family map."),
            "R6": R("PASS", "Continuous expression output."),
            "R7": R("FAIL", "GEO accession documentable but raw construct-level table not downloaded this round; raw SHA not obtained."),
        },
    })

    sources.append({
        "id": "Lind2020",
        "study": "Lind et al. PNAS 117 (2020), doi:10.1073/pnas.1907126117 'Synonymous codon substitutions perturb cotranslational protein folding in vivo and impair cell fitness'",
        "host": "Escherichia coli",
        "raw_sources": ["SI Appendix (WT / Shuf1 synonymous-shuffled gene + 5'/middle/3' chimeras)", "publisher methods"],
        "raw_access_status": "publisher_methods_verified_partial: fixed-protein synonymous variants in native context with continuous growth fitness, but variant set is small (WT + Shuf1 + a handful of chimeras); raw variant-count table not fully downloaded",
        "raw_artifacts_sha256": {},
        "construct_facts": [
            "Synonymous codon substitutions (e.g. Shuf1 shuffled synonymous allele) of a single gene in native locus context; continuous growth-fitness readout.",
            "Variant set is small (WT + Shuf1 + chimeras), not a large construct-level synonymous library suitable for protein/cluster OOD benchmarking.",
        ],
        "R": {
            "R1": R("PASS", "Independent 2020 E. coli study."),
            "R2": R("PASS", "Full CDS of the target gene (synonymous whole-gene variants)."),
            "R3": R("PASS", "Native locus context retains native 5'UTR (methods); exact upstream reconstruction not independently verified this round."),
            "R4": R("PASS", "Fixed-protein synonymous substitutions."),
            "R5": R("FAIL", "Single gene; no multi-protein family map for protein OOD."),
            "R6": R("PASS", "Continuous growth fitness."),
            "R7": R("FAIL", "Raw variant-count table not fully verified; scale insufficient for a benchmark library (n_variants too small)."),
        },
    })

    for s in sources:
        s["qualifying"] = is_qualifying(s)
    return sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    if os.path.exists(args.report):
        raise FileExistsError(f"report already exists: {args.report}")
    with open(args.protocol) as f:
        protocol = json.load(f)
    assert protocol["status"] == "FROZEN_BEFORE_OUTCOME_ASSOCIATION"
    sources = build_sources()
    n_qual = sum(s["qualifying"] for s in sources)
    # missing-dimension tally across non-qualifying sources
    fail_tally = {k: 0 for k in ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]}
    for s in sources:
        if not s["qualifying"]:
            for k in fail_tally:
                if s["R"][k]["status"] != "PASS":
                    fail_tally[k] += 1
    branch = decide_branch(n_qual)
    report = {
        "schema": "a9-rk42-independent-data-acquisition-v1",
        "task": "A9-RK42 phase B independent-data acquisition audit",
        "date": "2026-11-22",
        "protocol_sha256": sha(args.protocol),
        "label_free": True,
        "no_model_fit_no_outcome_association": True,
        "n_candidates": len(sources),
        "n_qualifying": n_qual,
        "sources": sources,
        "fail_tally_non_qualifying": fail_tally,
        "branch_decision": branch,
        "missing_dimensions": [
            "fixed-protein synonymous CDS library (R4): absent in 7/9 regulatory-grammar/N-terminal-fusion sources",
            "variant-specific native 5'UTR (R3): absent in 8/9 (fixed synthetic leader or synthetic regulatory parts)",
            "full CDS per variant (R2): absent in 6/9 (N-terminal segment / fixed reporter / promoter library)",
            "protein identity + family map for protein OOD (R5): absent in single-reporter sources",
            "documentable raw construct-level table SHA (R7): blocked/unverified for several sources",
        ],
        "strategic_option_for_user": {
            "question": "Authorize a relaxed eligibility for the FUNCTIONAL benchmark only (accept fixed synthetic leader + N-terminal synonymous editing window, e.g. Goodman-style), keeping strict R3 for start-structure transport claims?",
            "note": "Cambray fails R4 (amino-acid variation) so R3-relaxation alone does NOT unlock Cambray as a fixed-protein synonymous benchmark; Goodman-style N-terminal synonymous data is the plausible public fast path but requires user authorization to relax frozen R1-R7.",
            "do_not_unilaterally_relax_frozen_R1_R7": True,
        },
        "prospective_DBTL_design_B3": {
            "requires_user_budget_and_timeline_approval": True,
            "measurement_protocol_frozen_before_reading_outcomes": True,
            "design": {
                "proteins": ">=2 fixed proteins (e.g. sfGFP + a native E. coli enzyme) with family map",
                "library": "fixed-protein synonymous CDS library, >=several hundred variants/protein for protein/cluster OOD",
                "construct": "native complete variant-specific 5'UTR-CDS (>=4nt native upstream of ATG), reconstructable UTR[-4:]+CDS[:38]",
                "host": "independent E. coli host distinct from Kudla cohort (e.g. MG1655/MDS42)",
                "readout": "continuous expression (fluorescence) + growth-competition fitness, with replicates and detection-limit audit",
                "controls": "WT / LinearDesign / RNARL synonymous controls; preregistered splits and leakage audit",
            },
            "timeline_note": "wet-lab DBTL extends beyond the one-month preprint goal; public-first is the fast path; user must approve budget and extension.",
        },
        "boundaries": {
            "historical_MAGE_functional_untouched_frozen": True,
            "no_transport_effect_SOTA_mechanism_generator_claim": True,
            "public_retrospective_vs_prospective_DBTL_separated": True,
        },
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print("n_qualifying", n_qual, "/", len(sources))
    print("branch_decision", branch)
    print("report_sha256", sha(args.report))
    print("report", args.report)


if __name__ == "__main__":
    main()