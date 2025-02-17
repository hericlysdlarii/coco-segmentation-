import json
import os
import random
import cv2
from glob import glob
import torch
from torch.utils.data import Dataset, DataLoader, Subset
from tqdm import tqdm
import albumentations as A
from albumentations.pytorch import ToTensorV2
from torch.nn.utils.rnn import pad_sequence
# from torchvision import transforms
from transformers import AutoTokenizer


class Data(Dataset):
    def __init__(self, image_dir: str, image_split: str, caption_split: str, transform=None) -> None:
        self._image_dir = image_dir
        self._image_paths = glob(f'{image_dir}/{image_split}/*.jpg')
        self._caption_file_train = f'{image_dir}/{caption_split}/train_captions.json'
        self._caption_file_val = f'{image_dir}/{caption_split}/val_captions.json'
        self._transform = transform

        # Inicializa o tokenizador uma vez durante a inicialização
        self.tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

        # Carrega as legendas de acordo com a divisão de dados (train ou val)
        try:
            if image_split == 'train2017':
                with open(self._caption_file_train, 'r') as f:
                    self._captions = json.load(f)
            else:
                with open(self._caption_file_val, 'r') as f:
                    self._captions = json.load(f)
        except FileNotFoundError:
            print(f"Caption file for {image_split} not found.")
            self._captions = {}  # Usa um dicionário vazio como fallback

    def __len__(self) -> int:
        return len(self._image_paths)
    

    def __getitem__(self, idx: int) -> tuple:
        image_path = self._image_paths[idx]
        
        # Carrega a imagem com tratamento de erros
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Image not found at {image_path}")
        
        # Obtém o ID da imagem para recuperar a legenda correspondente
        image_id = str(int(os.path.basename(image_path).split('.')[0]))
        
        # Tenta recuperar a legenda correspondente ao ID da imagem
        image_captions = [anno['captions'] for anno in self._captions if str(int(anno['image_id'])) == image_id]
        
        if not image_captions:
            print(f"No captions found for image ID {image_id}. Returning an empty caption.")
            # captions = "<empty>"
        # else:
        #     selected_caption = random.choice(4)
    
        captions = []
        for cap in image_captions:
            captions = cap

        result = random.randint(0, (len(captions)-1))
        
        tokens = self.tokenizer(
            str(captions[result].strip()), 
            return_tensors="pt", 
            padding="longest", 
            truncation=True, 
            max_length=512
        )

        caption_ids = tokens["input_ids"].squeeze()

        caption_tensor = torch.tensor(caption_ids, dtype=torch.long)

        if self._transform:
            augmented = self._transform(image=image)
            image = augmented['image']

        return image, caption_tensor

class Data_test(Dataset):
    def __init__(self, image_dir: str, image_split: str, transform=None) -> None:
        self._image_dir = image_dir
        self._image_paths = glob(f'{image_dir}/{image_split}/*.jpg')
        self._transform = transform

    def __len__(self) -> int:
        return len(self._image_paths)

    def __getitem__(self, idx: int) -> tuple:
        image_path = self._image_paths[idx]
        
        # Carrega a imagem com tratamento de erros
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Image not found at {image_path}")

        if self._transform:
            augmented = self._transform(image=image)
            image = augmented['image']

        return image
    

class MyPreProcessing:
    def __init__(self):
        self.available_keys = set()

    def __call__(self, image):
        image = (image/255.).astype('float32')
        return {'image': image}


class Dataloader:
    def __init__(self, batch_size: int, size: int, shuffle: bool, subset: int = 0) -> None:
        self._batch_size = batch_size
        self._shuffle = shuffle
        self._subset = subset
        self._dir = '/home/hericlysdlarii/Projeto/coco-project/coco2017'
        self._size = size
        self._prob_aug = {
            'train2017': 0.5,
            'val2017': 0.,
            'test2017': 0.,
        }
    
    def _transform(self, image_split: str) -> A.Compose:
        p = self._prob_aug[image_split]
        
        return A.Compose([
           
            A.Resize(height=self._size, width=self._size),
            A.RandomBrightnessContrast(p=p),
            A.HueSaturationValue(p=p),

            A.HorizontalFlip(p=p),
            A.VerticalFlip(p=p),
            # A.RandomRotate90(p=p),

            MyPreProcessing(),
            ToTensorV2(),

        ])
    
    def _collate_fn(self, batch):
        # print('Batch: ', batch)
        
        images, captions = zip(*batch)  # Separa imagens e legendas
        images = torch.stack(images, 0)  # Empilha as imagens no batch

        # Adiciona padding nas legendas para que tenham o mesmo comprimento
        captions = pad_sequence(captions, batch_first=True, padding_value=0)  # 0 para token de padding

        return images, captions

    def get_dataloader(self, image_split: str, caption_split: str=None) -> DataLoader:
        if image_split == 'test2017':
            dataset = Data_test(self._dir, image_split, self._transform(image_split))

            if self._subset:
                dataset = Subset(dataset, range(self._subset))

            dataloader = DataLoader(dataset, batch_size=self._batch_size, shuffle=self._shuffle)

            return dataloader
        
        else:
            dataset = Data(self._dir, image_split, caption_split, self._transform(image_split))

            if self._subset:
                dataset = Subset(dataset, range(self._subset))

            dataloader = DataLoader(dataset, batch_size=self._batch_size, shuffle=self._shuffle, collate_fn=self._collate_fn) #
            
            return dataloader


    def get_train_dataloader(self) -> DataLoader: return self.get_dataloader('train2017', 'captions')
    def get_val_dataloader(self) -> DataLoader: return self.get_dataloader('val2017', 'captions')
    def get_test_dataloader(self) -> DataLoader: return self.get_dataloader('test2017')


