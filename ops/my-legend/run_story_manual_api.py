"""Local manual story test: real business/session API with two explicit test roles.

The production character picker depends on licensed stage assets. This local
entry supplies story-only identities without loading or changing those assets.
"""
import os
from my_legend_production.story_api import create_app


def main():
    if os.environ.get('MY_LEGEND_MANUAL_STORY_TEST') != '1':
        raise RuntimeError('MANUAL_STORY_TEST_FLAG_REQUIRED')
    app = create_app()
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', '') != '/api/v1/characters']

    @app.get('/api/v1/characters')
    def roles():
        return {'code': 0, 'message': 'ok', 'data': [
            dict(id=cid, name=name, description='故事人工测试角色，不绑定舞台素材', avatarUrl='', owned=True)
            for cid, name in [('legend-moyu', '墨羽'), ('legend-lingmo', '灵墨')]]}

    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8895, access_log=False)


if __name__ == '__main__':
    main()
