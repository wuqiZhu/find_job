import subprocess
import json
import re
import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CAREER_OPS_DIR = os.environ.get('CAREER_OPS_DIR', '/opt/career-ops')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
NODE_BIN = os.environ.get('NODE_BIN', 'node')


def parse_score_from_output(output):
    score_match = re.search(
        r'---SCORE_SUMMARY---\s*\n(.*?)\n---END_SCORE_SUMMARY---',
        output, re.DOTALL
    )
    if score_match:
        summary = score_match.group(1)
        result = {}
        for line in summary.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                result[key.strip()] = value.strip()
        return result

    score_line = re.search(r'(?:Score|SCORE)[：:\s]*(\d+\.?\d*)', output)
    if score_line:
        return {'SCORE': score_line.group(1)}

    return None


def normalize_score(score_raw):
    try:
        s = float(score_raw)
        if s <= 5:
            return round(s * 20, 1)
        return round(s, 1)
    except (ValueError, TypeError):
        return 0.0


def run_evaluation(jd_text):
    env = os.environ.copy()
    if GEMINI_API_KEY:
        env['GEMINI_API_KEY'] = GEMINI_API_KEY

    result = subprocess.run(
        [NODE_BIN, 'gemini-eval.mjs', '--no-save', jd_text],
        capture_output=True,
        text=True,
        cwd=CAREER_OPS_DIR,
        timeout=180,
        env=env
    )
    return result.stdout + result.stderr


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})


@app.route('/evaluate', methods=['POST'])
def evaluate():
    data = request.get_json(force=True, silent=True)
    if not data or 'jd' not in data:
        return jsonify({'error': 'Missing "jd" field in request body'}), 400

    jd_text = data['jd']
    company = data.get('company', 'Unknown')
    role = data.get('role', 'Unknown')

    if not jd_text.strip():
        return jsonify({'error': 'Empty "jd" field'}), 400

    logger.info(f"Evaluating: {company} - {role}")

    try:
        output = run_evaluation(jd_text)
        score_info = parse_score_from_output(output)

        score_raw = score_info.get('SCORE', '0') if score_info else '0'
        score_100 = normalize_score(score_raw)

        response = {
            'company': company,
            'role': role,
            'score': score_100,
            'score_raw': score_raw,
            'archetype': score_info.get('ARCHETYPE', '') if score_info else '',
            'legitimacy': score_info.get('LEGITIMACY', '') if score_info else '',
            'report': output[:5000],
            'success': True
        }

        logger.info(f"Result: {company} - {role} => score={score_100}")
        return jsonify(response)

    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout: {company} - {role}")
        return jsonify({'error': 'Evaluation timed out (180s)', 'success': False}), 504
    except Exception as e:
        logger.error(f"Error evaluating {company} - {role}: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/evaluate-batch', methods=['POST'])
def evaluate_batch():
    data = request.get_json(force=True, silent=True)
    if not data or 'jobs' not in data:
        return jsonify({'error': 'Missing "jobs" field'}), 400

    jobs = data['jobs']
    if len(jobs) > 10:
        return jsonify({'error': 'Max 10 jobs per batch'}), 400

    results = []
    for job in jobs:
        jd = job.get('jd', '')
        company = job.get('company', 'Unknown')
        role = job.get('role', 'Unknown')

        if not jd.strip():
            results.append({'company': company, 'role': role, 'error': 'Empty JD', 'success': False})
            continue

        try:
            output = run_evaluation(jd)
            score_info = parse_score_from_output(output)
            score_raw = score_info.get('SCORE', '0') if score_info else '0'
            score_100 = normalize_score(score_raw)

            results.append({
                'company': company,
                'role': role,
                'score': score_100,
                'score_raw': score_raw,
                'archetype': score_info.get('ARCHETYPE', '') if score_info else '',
                'success': True
            })
        except subprocess.TimeoutExpired:
            results.append({'company': company, 'role': role, 'error': 'Timeout', 'success': False})
        except Exception as e:
            results.append({'company': company, 'role': role, 'error': str(e), 'success': False})

    success_count = sum(1 for r in results if r.get('success'))
    logger.info(f"Batch complete: {success_count}/{len(jobs)} successful")
    return jsonify({'results': results, 'total': len(jobs), 'success': success_count})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting scoring service on port {port}")
    logger.info(f"CAREER_OPS_DIR: {CAREER_OPS_DIR}")
    app.run(host='0.0.0.0', port=port, debug=False)
