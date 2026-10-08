from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..database import get_db
from ..deps import Ctx, agora, get_ctx, requer_admin
from ..models import Empresa, Unidade, Usuario, UsuarioUnidade
from ..ratelimit import ip_cliente, limite_cadastro, limite_login
from ..schemas import (AlterarSenhaIn, LoginIn, RedefinirSenhaIn, RegistrarEmpresaIn, TokenOut,
                       UsuarioIn, UsuarioOut, UsuarioUpdate)
from ..security import (criar_token, hash_senha, senha_precisa_rehash, validar_forca_senha,
                        verificar_senha)

router = APIRouter(tags=["auth"])


def usuario_out(db: Session, u: Usuario) -> UsuarioOut:
    ids = [i for (i,) in db.execute(select(UsuarioUnidade.unidade_id).where(UsuarioUnidade.usuario_id == u.id))]
    if u.perfil == "admin":
        ids = [i for (i,) in db.execute(select(Unidade.id).where(Unidade.empresa_id == u.empresa_id))]
    return UsuarioOut(id=u.id, empresa_id=u.empresa_id, nome=u.nome, email=u.email, perfil=u.perfil,
                      ativo=u.ativo, unidade_ids=sorted(ids))


def _token(db: Session, u: Usuario) -> TokenOut:
    tok, exp = criar_token(u.id, u.token_versao)
    return TokenOut(access_token=tok, expires_in=exp, usuario=usuario_out(db, u))


def _checar_senha(senha: str) -> None:
    erro = validar_forca_senha(senha)
    if erro:
        raise HTTPException(422, erro)


# ------------------------------------------------------------------ público
@router.post("/auth/registrar", response_model=TokenOut, status_code=201)
def registrar(dados: RegistrarEmpresaIn, request: Request, db: Session = Depends(get_db)):
    """Cadastro self-service: cria a empresa, a primeira unidade e o administrador."""
    if not get_settings().permitir_cadastro_publico:
        raise HTTPException(403, "O cadastro público está desabilitado. Peça um convite ao administrador.")
    limite_cadastro.checar(ip_cliente(request))
    _checar_senha(dados.senha)
    email = dados.email.lower()
    if db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise HTTPException(409, "Este e-mail já está cadastrado.")
    emp = Empresa(nome=dados.empresa_nome, segmento=dados.segmento)
    db.add(emp)
    db.flush()
    uni = Unidade(empresa_id=emp.id, nome=dados.unidade_nome)
    usr = Usuario(empresa_id=emp.id, nome=dados.nome, email=email, senha_hash=hash_senha(dados.senha),
                  perfil="admin")
    db.add_all([uni, usr])
    db.flush()
    db.add(UsuarioUnidade(usuario_id=usr.id, unidade_id=uni.id))
    audit.registrar(db, emp.id, usr.id, "empresa.criar", "empresa", emp.id, None, audit.snap(emp), ip_cliente(request))
    db.commit()
    return _token(db, usr)


@router.post("/auth/login", response_model=TokenOut)
def login(dados: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = ip_cliente(request)
    limite_login.checar(ip)
    s = get_settings()
    u = db.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))
    invalido = HTTPException(401, "E-mail ou senha inválidos.")
    if u is None:
        verificar_senha(dados.senha, None)  # gasta o mesmo tempo
        raise invalido
    agora_ = agora()
    if u.bloqueado_ate and u.bloqueado_ate > agora_:
        raise HTTPException(423, "Conta temporariamente bloqueada por tentativas inválidas. Tente mais tarde.")
    if not verificar_senha(dados.senha, u.senha_hash):
        u.falhas_login += 1
        if u.falhas_login >= s.max_tentativas_login:
            u.bloqueado_ate = agora_ + timedelta(minutes=s.bloqueio_minutos)
            u.falhas_login = 0
        audit.registrar(db, u.empresa_id, u.id, "auth.login_falha", "usuario", u.id, ip=ip)
        db.commit()
        raise invalido
    emp = db.get(Empresa, u.empresa_id)
    if not u.ativo or not emp or not emp.ativa:
        raise invalido
    u.falhas_login, u.bloqueado_ate, u.ultimo_login = 0, None, agora_
    if senha_precisa_rehash(u.senha_hash):
        u.senha_hash = hash_senha(dados.senha)
    audit.registrar(db, u.empresa_id, u.id, "auth.login", "usuario", u.id, ip=ip)
    db.commit()
    return _token(db, u)


# ------------------------------------------------------------------ sessão
@router.post("/auth/renovar", response_model=TokenOut)
def renovar(ctx: Ctx = Depends(get_ctx)):
    return _token(ctx.db, ctx.usuario)


@router.get("/auth/eu", response_model=UsuarioOut)
def eu(ctx: Ctx = Depends(get_ctx)):
    return usuario_out(ctx.db, ctx.usuario)


@router.post("/auth/alterar-senha", status_code=204)
def alterar_senha(dados: AlterarSenhaIn, ctx: Ctx = Depends(get_ctx)):
    if not verificar_senha(dados.senha_atual, ctx.usuario.senha_hash):
        raise HTTPException(400, "Senha atual incorreta.")
    _checar_senha(dados.nova_senha)
    ctx.usuario.senha_hash = hash_senha(dados.nova_senha)
    ctx.usuario.token_versao += 1  # encerra as outras sessões
    ctx.auditar("auth.alterar_senha", "usuario", ctx.usuario.id)
    ctx.db.commit()


# ------------------------------------------------------------------ usuários (admin)
def _validar_unidades(ctx: Ctx, ids: list[int]) -> list[int]:
    ids = sorted(set(ids))
    if ids:
        validas = set(ctx.db.scalars(select(Unidade.id).where(Unidade.empresa_id == ctx.empresa_id,
                                                              Unidade.id.in_(ids))))
        if validas != set(ids):
            raise HTTPException(422, "Unidade inválida.")
    return ids


def _outro_admin_ativo(ctx: Ctx, excluir_id: int) -> bool:
    return bool(ctx.db.scalar(select(func.count(Usuario.id)).where(
        Usuario.empresa_id == ctx.empresa_id, Usuario.perfil == "admin", Usuario.ativo.is_(True),
        Usuario.id != excluir_id)))


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios(ctx: Ctx = Depends(requer_admin)):
    us = ctx.db.scalars(select(Usuario).where(Usuario.empresa_id == ctx.empresa_id).order_by(Usuario.nome))
    return [usuario_out(ctx.db, u) for u in us]


@router.post("/usuarios", response_model=UsuarioOut, status_code=201)
def criar_usuario(dados: UsuarioIn, ctx: Ctx = Depends(requer_admin)):
    _checar_senha(dados.senha)
    email = dados.email.lower()
    if ctx.db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise HTTPException(409, "Este e-mail já está cadastrado.")
    ids = _validar_unidades(ctx, dados.unidade_ids)
    u = Usuario(empresa_id=ctx.empresa_id, nome=dados.nome, email=email, senha_hash=hash_senha(dados.senha),
                perfil=dados.perfil)
    ctx.db.add(u)
    ctx.db.flush()
    ctx.db.add_all(UsuarioUnidade(usuario_id=u.id, unidade_id=i) for i in ids)
    ctx.auditar("usuario.criar", "usuario", u.id, None, {**audit.snap(u), "unidade_ids": ids})
    ctx.db.commit()
    return usuario_out(ctx.db, u)


def _usuario(ctx: Ctx, uid: int) -> Usuario:
    u = ctx.db.get(Usuario, uid)
    if not u or u.empresa_id != ctx.empresa_id:
        raise HTTPException(404, "Registro não encontrado.")
    return u


@router.patch("/usuarios/{uid}", response_model=UsuarioOut)
def atualizar_usuario(uid: int, dados: UsuarioUpdate, ctx: Ctx = Depends(requer_admin)):
    u = _usuario(ctx, uid)
    antes = {**audit.snap(u), "unidade_ids": usuario_out(ctx.db, u).unidade_ids}
    campos = dados.model_dump(exclude_unset=True)
    perde_admin = u.perfil == "admin" and (campos.get("perfil", "admin") != "admin" or campos.get("ativo") is False)
    if perde_admin and not _outro_admin_ativo(ctx, u.id):
        raise HTTPException(409, "É preciso manter ao menos um administrador ativo.")
    if u.id == ctx.usuario.id and campos.get("ativo") is False:
        raise HTTPException(409, "Você não pode desativar o próprio usuário.")
    if "unidade_ids" in campos:
        ids = _validar_unidades(ctx, campos.pop("unidade_ids") or [])
        ctx.db.query(UsuarioUnidade).filter(UsuarioUnidade.usuario_id == u.id).delete()
        ctx.db.add_all(UsuarioUnidade(usuario_id=u.id, unidade_id=i) for i in ids)
    sensivel = ("perfil" in campos and campos["perfil"] != u.perfil) or campos.get("ativo") is False
    for k, v in campos.items():
        setattr(u, k, v)
    if sensivel:
        u.token_versao += 1
    ctx.db.flush()
    ctx.auditar("usuario.atualizar", "usuario", u.id, antes,
                {**audit.snap(u), "unidade_ids": usuario_out(ctx.db, u).unidade_ids})
    ctx.db.commit()
    return usuario_out(ctx.db, u)


@router.post("/usuarios/{uid}/redefinir-senha", status_code=204)
def redefinir_senha(uid: int, dados: RedefinirSenhaIn, ctx: Ctx = Depends(requer_admin)):
    u = _usuario(ctx, uid)
    _checar_senha(dados.nova_senha)
    u.senha_hash = hash_senha(dados.nova_senha)
    u.token_versao += 1
    u.falhas_login, u.bloqueado_ate = 0, None
    ctx.auditar("usuario.redefinir_senha", "usuario", u.id)
    ctx.db.commit()
