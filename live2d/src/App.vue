<template>
  <div id="live2d-container">
    <canvas id="live2d-canvas" ref="canvasRef"></canvas>
  </div>
</template>

<script setup>
import { onMounted,onBeforeUnmount,watch, ref } from 'vue';
import { QWebChannel } from 'qwebchannel'

const canvasRef = ref(null);

let app;
let model;
let web_bridget=null

window.CLEAR=()=>{
  console.log("Web正在释放资源...")
  if(model){
    model.destroy(true, { children: true, texture: true });
    console.log("✅ 模型已销毁");
  }
  if(app){
    app.destroy(true, { children: true, texture: true });
    console.log("✅ 渲染已关闭");
  }
  if(web_bridget){
    console.log("📡 Web发出清除结束信号")
    web_bridget.web_done_set()
  }
}

function initInteractions() {
  app.stage.interactive = true;
  app.stage.hitArea = app.screen;

  let dragData = null;
  let offset = { x: 0, y: 0 };

  app.stage.on('pointerdown', (event) => {
    dragData = event.data;
    const newPosition = dragData.getLocalPosition(model.parent);
    offset.x = newPosition.x - model.x;
    offset.y = newPosition.y - model.y;
  });

  app.stage.on('pointermove', () => {
    if (dragData) {
      const newPosition = dragData.getLocalPosition(model.parent);
      model.x = newPosition.x - offset.x;
      model.y = newPosition.y - offset.y;
    }
  });

  app.stage.on('pointerup', () => { dragData = null; });

  window.addEventListener('wheel', (event) => {
    const zoomIntensity = 0.1;
    const scrollDirection = event.deltaY > 0 ? -1 : 1;
    const factor = Math.pow(1 + zoomIntensity, scrollDirection);
    let newScale = model.scale.x * factor;
    model.scale.set(Math.max(0.05, Math.min(2.0, newScale)));
  }, { passive: false });
}

window.offset_y = 0;

async function initLive2D() {
  app = new PIXI.Application({
    view: canvasRef.value,
    autoStart: true,
    resizeTo: window,
    backgroundAlpha: 1,
    antialias: true,
    preserveDrawingBuffer: true
  });

  try {
    const backgroundSprite=PIXI.Sprite.from("background/bk4.png");
    backgroundSprite.anchor.set(0.5);
    app.stage.addChild(backgroundSprite);

    const resizeBackground = () => {
        if (!backgroundSprite || !backgroundSprite.texture.valid) return;
        const screenWidth = app.screen.width;
        const screenHeight = app.screen.height;
        const scale = Math.max(screenWidth / backgroundSprite.texture.width, screenHeight / backgroundSprite.texture.height);
        backgroundSprite.scale.set(scale);
        backgroundSprite.x = screenWidth / 2;
        backgroundSprite.y = screenHeight / 2;
    };

    if (backgroundSprite.texture.baseTexture.valid) {
        resizeBackground();
    } else {
        backgroundSprite.texture.once('update', resizeBackground);
    }

    model = await PIXI.live2d.Live2DModel.from("models/QianYi/QianYi.model3.json");
    window.model=model
    app.stage.addChild(model);

    model.scale.set(0.16);
    model.anchor.set(0.5, 0.5);

    const resizeModel = (offset=null) => {
        if (!model) return;

        if (offset!=null){window.offset_y=offset}

        console.log(window.offset_y)
        model.x = app.screen.width / 3;
        model.y = app.screen.height * 1.1-window.offset_y; 
    };
    window.resizeModel = resizeModel;
    resizeModel();

    const onResize = () => {
        requestAnimationFrame(() => {
            resizeBackground();
            resizeModel();
        });
    };
    app.renderer.on('resize', onResize);

    await model.internalModel.coreModel.setParameterValueById('Param123', 1.0);
    initInteractions();

  } catch (error) {
    console.error("❌ 加载失败：", error);
  }
}

onMounted(async () => {
  await initLive2D();
  console.log("web初始化成功")
  if (window.qt && window.qt.webChannelTransport){
    new QWebChannel(window.qt.webChannelTransport,(channel)=>{
      web_bridget=channel.objects.web_bridget;
      console.log("✅ WebChannel 连接成功");
    })
  }
});

</script>
