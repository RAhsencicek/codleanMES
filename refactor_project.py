import os
import shutil
import re

file_maps = {
    'data_validator.py': 'src/core',
    'state_store.py': 'src/core',
    'kafka_consumer.py': 'src/core',
    
    'threshold_checker.py': 'src/analysis',
    'trend_detector.py': 'src/analysis',
    'risk_scorer.py': 'src/analysis',
    
    'alert_engine.py': 'src/alerts',
    
    'dashboard_pro.py': 'src/ui',
    
    'hpr_monitor.py': 'src/app',
    'mock_hpr_monitor.py': 'src/app',
    
    'limits_config.yaml': 'config',
    'ml_iyilestirme_analizi.md.resolved': 'docs',
    'pipeline_mimarisi.md': 'docs',
    
    'train_model.py': 'scripts/ml_tools',
    'prepare_ml_data.py': 'scripts/ml_tools',
    
    'batch_alert_analysis.py': 'scripts/data_tools',
    'batch_violation_analysis.py': 'scripts/data_tools',
    'window_collector.py': 'scripts/data_tools',
    'demo_alert_generation.py': 'scripts/data_tools',
    'diagnose_kafka_connection.py': 'scripts/data_tools',
    'generate_technician_report.py': 'scripts/data_tools',
    'analyze_live_windows.py': 'scripts/data_tools',
    'validation_sampling.py': 'scripts/data_tools',
    'live_kafka_test_analysis.py': 'scripts/data_tools',
    'code_review_and_system_critique.py': 'scripts/data_tools'
}

module_to_package = {f.replace('.py', ''): path.replace('/', '.') for f, path in file_maps.items() if f.endswith('.py')}

def run():
    base_dir = '/Users/mac/kafka'
    
    dirs = ['src/core', 'src/analysis', 'src/alerts', 'src/app', 'src/ui', 'tests', 
            'scripts/ml_tools', 'scripts/data_tools', 'config', 'docs', 'data', 'logs', 'models']
    
    for d in dirs:
        os.makedirs(os.path.join(base_dir, d), exist_ok=True)
        if d.startswith('src/'):
            with open(os.path.join(base_dir, d, '__init__.py'), 'w') as f:
                pass
    with open(os.path.join(base_dir, 'src', '__init__.py'), 'w') as f:
        pass
        
    for f in os.listdir(base_dir):
        if os.path.isdir(os.path.join(base_dir, f)):
            continue
            
        if f.startswith('test_') and f.endswith('.py'):
            shutil.move(os.path.join(base_dir, f), os.path.join(base_dir, 'tests', f))
            continue
            
        if f.endswith('.log'):
            shutil.move(os.path.join(base_dir, f), os.path.join(base_dir, 'logs', f))
            continue
            
        if f.endswith('.csv') or (f.endswith('.json') and f != 'state.json' and f != 'live_windows.json'):
            shutil.move(os.path.join(base_dir, f), os.path.join(base_dir, 'data', f))
            continue
            
        if f in file_maps:
            shutil.move(os.path.join(base_dir, f), os.path.join(base_dir, file_maps[f], f))
            
    for root, dirs, files in os.walk(base_dir):
        if 'venv' in root or '.git' in root or '__pycache__' in root:
            continue
            
        for f in files:
            if f.endswith('.py') and f != 'refactor_project.py':
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    
                for mod, pkg in module_to_package.items():
                    content = re.sub(rf'^import {mod}\b', f'from {pkg} import {mod}', content, flags=re.MULTILINE)
                    content = re.sub(rf'^from {mod} import', f'from {pkg}.{mod} import', content, flags=re.MULTILINE)
                    
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(content)

if __name__ == '__main__':
    run()
