"""Keep manuscript evidence figures and supporting-table references coherent."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
PAPER=ROOT/'paper/wrr_tr'

def expand(path,seen=None):
    seen=set() if seen is None else seen
    path=path.resolve()
    if path in seen:raise ValueError('Circular TeX input')
    seen=seen|{path}
    text=path.read_text()
    def replace(match):
        name=match.group(1)
        nested=PAPER/(name if name.endswith('.tex') else name+'.tex')
        return expand(nested,seen) if nested.is_file() else match.group(0)
    return re.sub(r'\\input\{([^}]+)\}',replace,text)

def test_every_main_figure_is_cited_in_figure_order():
    content=expand(PAPER/'review_completion_article.tex')
    labels=re.findall(r'\\label\{(fig:[^}]+)\}',content)
    first=list(dict.fromkeys(re.findall(r'\\ref\{(fig:[^}]+)\}',content)))
    assert labels and len(labels)==len(set(labels))
    assert first==labels

def test_architecture_states_visible_and_hidden_information_boundaries():
    graph=(PAPER/'figures/architecture/fig1_evidence_actual.dot').read_text()
    assert 'Hidden target days are excluded from local fitting.' in graph
    assert 'Visible target and donor records remain usable.' in graph
    assert 'Fixed source annual models' in graph
    assert 'complete target observations enter only' not in graph.lower()
    methods=(PAPER/'simple_research_methods.tex').read_text()
    assert 'Unmasked target observations and neighboring physical stations remain available' in methods
    assert 'The complete reference, including those hidden days, is used for scoring' in methods
    assert 'hides every selected year' not in methods.lower()

def test_first_four_supporting_tables_match_main_text_references():
    supporting=(PAPER/'review_completion_supporting.tex').read_text()
    assert supporting.index(r'\input{focused_supporting_tables.tex}') < supporting.index(r'\input{simple_research_supporting.tex}')
    labels=re.findall(r'\\label\{(tab:[^}]+)\}',(PAPER/'focused_supporting_tables.tex').read_text())
    assert labels[:4]==['tab:focused-annual','tab:focused-source-release','tab:focused-matched-release','tab:focused-uncertainty']
    main=(PAPER/'review_completion_article.tex').read_text()
    for number in ['S1','S2','S3','S4']:
        assert 'Table '+number in main

def test_supporting_information_uses_unmodified_si_class_and_complete_contents():
    supporting=(PAPER/'review_completion_supporting.tex').read_text()
    template=ROOT/'paper/wrr/template/agutexSI2019.cls'
    assert supporting.startswith(r'\documentclass[draft,wrr]{agutexSI2019}')
    assert supporting.count(r'\begin{article}')==supporting.count(r'\end{article}')==1
    assert r'\ref{si:last-text-section}' in supporting
    assert r'\label{si:last-text-section}' in supporting
    assert r'\ref{tab:truckee-exploratory}' in supporting
    expanded=expand(PAPER/'review_completion_supporting.tex')
    assert r'\label{tab:truckee-exploratory}' in expanded
    article=expand(PAPER/'review_completion_article.tex')
    for name,text in (('article',article),('supporting',expanded)):
        labels=re.findall(r'\\label\{([^}]+)\}',text)
        duplicates=sorted({label for label in labels if labels.count(label)>1})
        assert not duplicates, name+' multiply-defined labels: '+', '.join(duplicates)
    leftover=['tab:time-support-legacy-weak','tab:time-support-legacy-report']
    assert all(label not in expanded and label not in article for label in leftover)
    report=(ROOT/'scripts/963_process_revision_report.py').read_text()
    assert 'save(fig, "03_time_support")' not in report
    assert 'save(fig, "03_time_support_legacy")' in report
