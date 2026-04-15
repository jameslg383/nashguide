from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from api.models.database import get_db
from api.models.content import BlogPost

router = APIRouter(tags=["blog"])


@router.get("/blog", response_class=HTMLResponse)
def blog_index(db: Session = Depends(get_db)):
    posts = (
        db.query(BlogPost)
        .filter(BlogPost.status == "published")
        .order_by(BlogPost.published_at.desc())
        .all()
    )
    links = "".join(
        f'<li><a href="/blog/{p.slug}">{p.title}</a> — <small>{p.meta_description or ""}</small></li>'
        for p in posts
    )
    return f"""<!doctype html><html><head><title>NashGuide AI Blog</title></head>
    <body style='font-family:system-ui;max-width:720px;margin:40px auto;padding:0 20px'>
    <h1>NashGuide AI Blog</h1><ul>{links or '<li>No posts yet.</li>'}</ul></body></html>"""


@router.get("/blog/{slug}", response_class=HTMLResponse)
def blog_post(slug: str, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter(BlogPost.slug == slug, BlogPost.status == "published").first()
    if not post:
        raise HTTPException(404, "Post not found")
    # minimal markdown->html: preserve newlines
    body = post.content_md.replace("\n\n", "</p><p>").replace("\n", "<br>")
    return f"""<!doctype html><html><head><title>{post.title}</title>
    <meta name='description' content='{post.meta_description or ""}'></head>
    <body style='font-family:system-ui;max-width:720px;margin:40px auto;padding:0 20px;line-height:1.6'>
    <a href='/blog'>← Blog</a><h1>{post.title}</h1><p>{body}</p></body></html>"""
